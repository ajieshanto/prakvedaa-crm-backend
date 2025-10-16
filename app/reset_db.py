from app.database import Base, engine

print("🔧 Resetting database...")
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
print("✅ Database reset successful.")
