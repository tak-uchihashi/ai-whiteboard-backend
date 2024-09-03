from pydantic import BaseModel
from typing import List, Dict

class Component(BaseModel):
    name: str
    type: str
    stereotype: str
    description: str
    attributes: List[Dict[str, str]]
    methods: List[Dict[str, str]]
    relationships: List[str]
    
class Diagram(BaseModel):
    id: int
    name: str
    diagramText: str

class Context(BaseModel):
    contextId: str 
    version: int
    backgroundRequirements: List[str]
    umlDiagrams: List[Diagram]
    componentList: List[Component]
    recentChanges: List[str]
    
class History(BaseModel):
    id: str
    systemId: str
    contextId: str
    version: str
    timestamp: str
    instruction: str
    aiAnswer: str