import os
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine, String, Text, ForeignKey, JSON, DateTime, BigInteger
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

def uid():
    return str(uuid4())

class Base(DeclarativeBase):
    pass

class Project(Base):
    __tablename__ = 'projects'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120))
    demo: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Record(Base):
    """Typed document records; project ownership is enforced through a foreign key."""
    __tablename__ = 'records'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class AIBudget(Base):
    __tablename__='ai_budgets'
    id: Mapped[str]=mapped_column(String(40),primary_key=True)
    calls: Mapped[int]=mapped_column(BigInteger,default=0)
    tokens: Mapped[int]=mapped_column(BigInteger,default=0)
    cost_micro: Mapped[int]=mapped_column(BigInteger,default=0)

from sqlalchemy.types import UserDefinedType
class VectorType(UserDefinedType):
    cache_ok=True
    def get_col_spec(self,**kw):return 'VECTOR(384)'

class ContextChunk(Base):
    __tablename__='context_chunks'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    project_id: Mapped[str]=mapped_column(ForeignKey('projects.id',ondelete='CASCADE'),index=True)
    version: Mapped[str]=mapped_column(String(64),index=True)
    encoder: Mapped[str]=mapped_column(String(80))
    path: Mapped[str]=mapped_column(String(200))
    start_line: Mapped[int]=mapped_column()
    end_line: Mapped[int]=mapped_column()
    content: Mapped[str]=mapped_column(Text())
    embedding: Mapped[str]=mapped_column(Text().with_variant(VectorType(),'postgresql'))

engine = create_engine(os.getenv('DATABASE_URL', 'sqlite:///./debugych.db'), hide_parameters=True, **({'connect_args': {'check_same_thread': False}} if os.getenv('DATABASE_URL', 'sqlite').startswith('sqlite') else {}))
Session = sessionmaker(engine, expire_on_commit=False)

def add_record(db, project_id, kind, data):
    row = Record(project_id=project_id, kind=kind, data=data)
    db.add(row)
    db.flush()
    return row

def serialize(row):
    if isinstance(row, Project):
        return {'id': row.id, 'name': row.name, 'demo': row.demo, 'created_at': row.created_at.isoformat()}
    return {'id': row.id, 'project_id': row.project_id, 'created_at': row.created_at.isoformat(), **row.data}
