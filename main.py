from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, List
import json
from openai import OpenAI
import os
from datetime import datetime
import csv
from dotenv import load_dotenv # pip3 install python-dotenv

from models import History 

load_dotenv()
os.environ['OPENAI_API_KEY'] = os.getenv("OPENAI_API_KEY")
os.environ['ORGANIZATION_ID'] = os.getenv("ORGANIZATION_ID")
os.environ['PROJECT_ID'] = os.getenv("PROJECT_ID")

app = FastAPI()

# 
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 必要に応じて許可するオリジンを設定
    allow_credentials=True,
    allow_methods=["*"],  # 必要に応じて許可するメソッドを設定
    allow_headers=["*"],
)

# シンプルなデータベースの代わりにメモリ内ストレージを使用
database = {
    "context": None,
    "history": []
}


class Context(BaseModel):
    contextId: str  
    version: int
    backgroundRequirements: list
    umlDiagrams: list
    componentList: list
    recentChanges: list

class UserInstruction(BaseModel):
    context: str
    version: str
    instruction: str


# ファイルパスの定義
system_id = os.environ["SYSTEM_ID"]
system_folder = "./" + system_id
history_file = "history.csv"
# context_folder = "contexts/"
os.makedirs("./" + system_id, exist_ok=True )

def save_to_history(system_id: str, context_id: str, version: int, instruction: str, ai_answer: str):
    timestamp = datetime.now().isoformat()
    history_data = {
        "id": system_id + "_" + context_id + "_v" + str(version),
        "systemId": system_id,
        "contextId": context_id,
        "version": version,
        "timestamp": timestamp,
        "instruction": instruction,
        "aiAnswer": ai_answer
    }

    # 履歴をCSVに保存
    history_file_path = os.path.join(system_folder, context_id, history_file)
    with open(history_file_path, mode='a', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=history_data.keys())
        if os.stat(history_file_path).st_size == 0:  # ファイルが空の場合、ヘッダーを書き込む
            writer.writeheader()
        writer.writerow(history_data)

def save_context_as_json(system_id: str, context_id: str, version: int, context: Dict):
    # ファイル名の作成
    filename = f"{system_id}_{context_id}_v{version}.json"
    filepath = os.path.join(system_folder, context_id, filename)

    # コンテキストをJSONファイルとして保存
    with open(filepath, 'w') as json_file:
        json.dump(context, json_file, indent=2)

@app.get("/context/", response_model=List[str])
def get_context_names():
    print('get context names')
    # ./systemディレクトリーの下のディレクトリー名の一覧を返す。
    context_names = [name for name in os.listdir(system_folder) if os.path.isdir(os.path.join(system_folder, name))]
    print(context_names)
    return context_names
    # if database["context"] is None:
    #     database["context"] = sample_context
    #     database["history"].append(sample_context)
    #     print('sample context')
    # return database["context"]

@app.get("/context/{context_id}/{id}", response_model=Context)
def get_context_by_id(context_id: str, id: str):
    print('get context by id' + id)
    # with open(os.path.join(system_folder , context_id, id)+".json", "r") as context_file:
    #     context_text = context_file.read()
    # print('get context by id')
    context = context_versions.get(id)
    if context is None:
        get_chat_history(context_id)
        context = context_versions['id']
    # print(context_text)
    # print(json.loads(context_text))
    return context

@app.post("/context/")
def create_context(context: Context):
    print("create new context:"+context.contextId)
    os.makedirs(os.path.join(system_folder, context.contextId), exist_ok=True)
    history_file_path = os.path.join(system_folder, context.contextId, history_file)
    with open(history_file_path, mode='w', newline='') as file:
        file.write("id,systemId,contextId,version,timestamp,instruction,aiAnswer\n")
    # save_context_as_json(system_id, context.contextId, context.version, context)
    name = system_id + "_" + context.contextId + "_v" + str(context.version)
    context_versions[name] = json.loads(context.model_dump_json())
    instruction_dict = {
        "context": context.contextId,
        "version": name,
        "instruction":"新規コンテキストを作成してください"
    }
    newInstruction = UserInstruction(**instruction_dict)
    message, updated_context, ai_answer = process_instruction(newInstruction)
    del context_versions[name]
    return {
        "message": message,
        "context": updated_context,
        "aiAnswer": ai_answer
    }


context_versions = {}
@app.get("/history/{context_id}", response_model=List[History])
def get_chat_history(context_id: str):
    # history.csvの各行の内容をDictinaryにして、Listとして返す。
    print('getting_history')
    history_file_path = os.path.join(system_folder, context_id, history_file)
    result = []
    with open(history_file_path, 'r') as history:
        reader = csv.DictReader(history)
        rows = list(reader)

    print('getting_context_versions')
    files = os.listdir(os.path.join(system_folder, context_id))    
    for file in files:
        if file.endswith(".json"):
            print('Loading:'+file)
            with open(os.path.join(system_folder , context_id, file), "r") as context_file:
                context_versions[file.replace(".json", "")] =  json.loads(context_file.read())

    return rows

@app.post("/instruction/")
def process_instruction(instruction: UserInstruction):
    print("instruction:")
    print(type(instruction))
    print(instruction)
    print("context keys")
    for key in context_versions.keys():
        print(key)
    print("context keys end")
    
    if context_versions.get(instruction.version) is None:
        raise HTTPException(status_code=404, detail="Context not found")

    # 現在のコンテキストを取得
    context = context_versions[instruction.version]
    print("context found")
    # context = database["context"]


    # AIにコンテキストの更新を依頼
    try:
        updated_context, ai_answer = update_context_with_ai(context, instruction.instruction)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI更新処理中にエラーが発生しました: {e}")

    # バージョンを更新
    # print(json.dump(updated_context))
    history_file_path = os.path.join(system_folder, context['contextId'], history_file)
    with open(history_file_path, 'r') as history:
        reader = csv.DictReader(history)
        versions = [int(row['version']) for row in reader]

    # 最大値を求める
    if len(versions) == 0:
        max_version = 1
    else:
        max_version = max(versions) + 1
    updated_context["version"] = max_version

    # 履歴とコンテキストを保存
    save_to_history(system_id, updated_context["contextId"], updated_context["version"], instruction.instruction, ai_answer)
    save_context_as_json(system_id, updated_context["contextId"], updated_context["version"], updated_context)

    # 更新されたコンテキストをデータベースに保存
    # database["context"] = updated_context
    # database["history"].append(updated_context)
    context_versions[system_id + "_" + context["contextId"] + "_v" + str(updated_context["version"])] = updated_context    

    # コンテキストとAIからの回答を含めて返す
    return {
        "message": "Instruction processed",
        "context": updated_context,
        "aiAnswer": ai_answer
    }


def generate_ai_prompt(context: Dict, instruction: str) -> str:
    prompt = f"""
    # ソフトウェアの設計文書についてこちらからの指示や相談に基づいて全体の整合性の取れた更新を行い、より良い設計のアドバイスをしてください。

    ## 現在の設計文書
    ```
    {json.dumps(context, indent=2)}
    ```

    ## 指示
    {instruction}

    ## 要件
    - ビジネス要求、コンポーネント定義、クラス図、シーケンス図、状態遷移図の整合性を必ず保持させること。
    - 回答は出力フォーマットのJSON形式で行ってください。回答はそのままPythonのjson.loads関数に渡されます。```で囲まないでください。
    - contextIdはキーとして使われます。現在の設計文書のcontextIdをそのまま使用してください。
    - umlDiagramsの各要素に@startuml @endumlは不要です。MermaidのDiagram Typeから記述してください。
    ### クラス設計ルール
    - クラス名はPascalCaseで記述してください。
    - 属性名、メソッド名、引数名、戻り値の型はcamelCaseで記述してください。
    - StereotypeはDomain Driven Design、Micro Service Patterns、Patterns of Enterprise Application Architectureなど広く知られた分類に沿って記述してください。
    - StereotypeはUML Class Diagramではnoteとして表現してください。例:note for User "<<Entity>>"
    - クラス間のRelationの種類を明確にしてください。CompositionとAggregationの場合は単方向として記述して関連先のCardinalityを明確にしてください。これらをUMLクラス図にも反映してください。
    - Value Objectを属性として持つ場合はCompositionとなります。
    - Aggregate内のEntity間の関連は全てCompositionとなります。
    - Aggregate外Entityへの関連はAggregationとなります。
    - シーケンス図の起点はclientとしてください。
    - 状態遷移図には状態を遷移させるイベントを明記してください。
    
    ### 出力フォーマット
    {{
      "context": {{
        "contextId": "string",
        "version": int,
        "backgroundRequirements": [
          ["string"]
        ],
        "umlDiagrams": [{{
          {{
              "id": int,
              "name": "string",
              "diagramText": "string"
           }}
        }}
        ],
        "componentList": [
          {{
            "name": "string",
            "type": "string",
            "stereotype": "string",
            "description": "string",
            "attributes": [
              {{
                "name": "string",
                "type": "string",
                "description": "string"
              }}
            ],
            "methods": [
              {{
                "name": "string",
                "returnType": "string",
                "parameters": [
                  {{
                    "name": "string",
                    "type": "string"
                  }}
                ],
                "description": "string"
              }}
            ],
            "relationships": ["string"]
          }}
        ],
        "recentChanges": ["string"]
      }},
      "aiAnswer": ["string"]
    }}
    - aiAnswerには、AIが行った変更内容、質問への回答などを、理由と共に出力してください。
    """
    return prompt


def update_context_with_ai(context: Dict, instruction: str) -> Dict:
    """
    AIにコンテキストの更新を依頼し、更新されたコンテキストを取得します。
    """
    prompt = generate_ai_prompt(context, instruction)

    client = OpenAI(
        organization=os.environ.get("ORGANIZATION_ID"),
        project=os.environ.get("PROJECT_ID"),
    )

    response = client.chat.completions.create(
        model='gpt-4o',
        messages=[
            {"role": "system", "content": "You are a professional IT Architect and a good advisor. You know everything about Domain Driven Design, Event Driven Architecture, PofEAA, Clean Architecture, SpringBoot and many modern programming languages. You are also a very fluent Japanese speaker."},
            {"role": "user", "content": prompt}
        ]
    )
    # AIの回答をパースして更新されたコンテキストを取得
    response = response.choices[0].message.content
    print(response)
    response_json = json.loads(response)
    updated_context = response_json["context"]
    ai_answer = response_json["aiAnswer"]

    return updated_context, ai_answer


# サンプルコンテキスト
sample_context = {
    "contextId": "CTX-123456", 
    "version": 2,
    "backgroundRequirements": [
            "要件 1: システムはマルチユーザーアクセスをサポートする必要があります。",
            "要件 2: すべてのデータは暗号化される必要があります。"
    ],
    "umlDiagrams":   # "uml_diagrams" を "umlDiagrams" に変更
        # "classDiagram": "classDiagram\nclass User {\n  +String name\n  +String email\n}\nclass Order {\n  +String orderId\n  +Date date\n}\nUser --> Order\n",            
        # "sequenceDiagram": "sequenceDiagram\nUser->>Order: 注文を行う\nOrder-->>User: 注文を確認する\n",
        # "stateTransitionDiagram": "stateDiagram\n[*] --> ログイン\nログイン --> ログアウト\n"
        [
         {"id":1,
          "diagramName":"Class Diagram",
          "diagramText":"classDiagram\nclass User {\n  +String name\n  +String email\n}\nclass Order {\n  +String orderId\n  +Date date\n}\nUser --> Order\n",            
         },
         {  
            "id":2,
            "diagramName":"Sequence Diagram",
            "diagramText":"sequenceDiagram\nUser->>Order: 注文を行う\nOrder-->>User: 注文を確認する\n",
        },
         {
            "id":3,
            "diagramName":"State Diagram",
            "diagramText":"stateDiagram\n[*] --> ログイン\nログイン --> ログアウト\n"
            }
        ]
    ,
    "componentList": [  # "component_list" を "componentList" に変更
        {
            "name": "User",
            "type": "Class",
            "stereotype": "エンティティ",  # "stereotype" はそのまま
            "description": "システム内のユーザーを表します。",
            "attributes": [
                {"name": "name", "type": "String", "description": "ユーザーの名前。"},
                {"name": "email", "type": "String", "description": "ユーザーのメールアドレス。"}
            ],
            "methods": [
                {
                    "name": "register",
                    "returnType": "void",
                    "parameters": [
                        {"name": "email", "type": "String"},
                        {"name": "password", "type": "String"}
                    ],
                    "description": "メールアドレスとパスワードを使って新しいユーザーを登録します。"
                },
                {
                    "name": "updateProfile",
                    "returnType": "void",
                    "parameters": [
                        {"name": "name", "type": "String"},
                        {"name": "email", "type": "String"}
                    ],
                    "description": "ユーザーの名前とメールアドレスを更新します。"
                }
            ],
            "relationships": ["Order"]
        },
        {
            "name": "Order",
            "type": "Class",
            "stereotype": "エンティティ",
            "description": "ユーザーが行った注文を表します。",
            "attributes": [
                {"name": "orderId", "type": "String", "description": "注文の一意の識別子。"},
                {"name": "date", "type": "Date", "description": "注文が行われた日付。"}
            ],
            "methods": [
                {
                    "name": "confirm",
                    "returnType": "void",
                    "parameters": [],
                    "description": "注文を確認します。"
                },
                {
                    "name": "cancel",
                    "returnType": "void",
                    "parameters": [],
                    "description": "注文をキャンセルします。"
                }
            ],
            "relationships": ["User"]
        }
    ],
    "recentChanges": [  # "recent_changes" を "recentChanges" に変更
        "クラス `User` を属性とメソッドで追加しました。",
        "`User` と `Order` 間の関係を定義しました。"
    ]
}

