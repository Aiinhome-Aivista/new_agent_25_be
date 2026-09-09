import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from backend.app.core.config import config
from backend.app.core.logging_config import logger

Base = declarative_base()
engine = None
SessionLocal = None
is_sqlite_fallback = False

def init_db():
    global engine, SessionLocal, is_sqlite_fallback
    
    mysql_uri = config.get_database_uri()
    try:
        logger.info(f"Attempting connection to MySQL at {config.MYSQL_HOST}:{config.MYSQL_PORT}...")
        
        # Test direct socket connection or database creation first
        try:
            import pymysql
            conn = pymysql.connect(
                host=config.MYSQL_HOST,
                port=config.MYSQL_PORT,
                user=config.MYSQL_USER,
                password=config.MYSQL_PASSWORD,
                connect_timeout=4
            )
            cursor = conn.cursor()
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {config.MYSQL_DATABASE} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as db_err:
            logger.warning(f"Could not auto-create MySQL database: {db_err}")

        engine = create_engine(
            mysql_uri,
            pool_recycle=3600,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 5}
        )
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        is_sqlite_fallback = False
        logger.info("Successfully connected to MySQL database.")
    except Exception as e:
        logger.error(f"MySQL connection failed or driver unavailable: {e}")
        if config.FALLBACK_TO_SQLITE:
            logger.warning("Falling back to local SQLite database (ai_code_review.db) for local execution reliability.")
            sqlite_path = os.path.join(os.path.dirname(__file__), "..", "..", "ai_code_review.db")
            engine = create_engine(
                f"sqlite:///{sqlite_path}",
                connect_args={"check_same_thread": False}
            )
            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            is_sqlite_fallback = True
        else:
            raise e

    # Import models and create tables
    from backend.app.models.entities import ReviewSession, AcceptanceCriteriaCheck, ReviewFinding, MissingTest, PassedCheck, CodingStandard, ReviewAuditLog
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified / created.")

def get_db():
    if SessionLocal is None:
        init_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
