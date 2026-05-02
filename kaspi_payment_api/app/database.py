from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import DATABASE_URL, SQL_ECHO

engine = create_engine(DATABASE_URL, echo=SQL_ECHO)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
