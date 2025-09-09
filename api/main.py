import os
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from datetime import datetime
from pydantic import BaseModel
from typing import List, Optional
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создание FastAPI приложения
app = FastAPI(
    title="🏸 Badminton Rating API",
    description="API для приложения бадминтон рейтинга",
    version="1.0.0"
)

# CORS настройки
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://vanporigon-tech.github.io",
        "http://localhost:8000",
        "http://127.0.0.1:8000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Настройка базы данных
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://user:password@localhost:5432/badminton"
)

# Исправляем URL для Vercel PostgreSQL
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Модели базы данных
class Player(Base):
    __tablename__ = "players"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    rating = Column(Integer, default=1500)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Связи
    rooms = relationship("Room", back_populates="creator")
    memberships = relationship("RoomMember", back_populates="player")

class Room(Base):
    __tablename__ = "rooms"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    creator_id = Column(Integer, ForeignKey("players.id"))
    max_players = Column(Integer, default=4)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Связи
    creator = relationship("Player", back_populates="rooms")
    members = relationship("RoomMember", back_populates="room")

class RoomMember(Base):
    __tablename__ = "room_members"
    
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id"))
    player_id = Column(Integer, ForeignKey("players.id"))
    is_leader = Column(Boolean, default=False)
    joined_at = Column(DateTime, default=datetime.utcnow)
    
    # Связи
    room = relationship("Room", back_populates="members")
    player = relationship("Player", back_populates="memberships")

# Создание таблиц
try:
    Base.metadata.create_all(bind=engine)
    logger.info("✅ Таблицы созданы успешно")
except Exception as e:
    logger.error(f"❌ Ошибка создания таблиц: {e}")

# Dependency для получения сессии БД
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pydantic модели
class PlayerCreate(BaseModel):
    telegram_id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None

class PlayerResponse(BaseModel):
    id: int
    telegram_id: int
    first_name: str
    last_name: Optional[str]
    username: Optional[str]
    rating: int
    
    class Config:
        from_attributes = True

class RoomCreate(BaseModel):
    name: str
    creator_telegram_id: int
    max_players: int = 4

class RoomMemberResponse(BaseModel):
    id: int
    player: PlayerResponse
    is_leader: bool
    joined_at: datetime
    
    class Config:
        from_attributes = True

class RoomResponse(BaseModel):
    id: int
    name: str
    creator_id: int
    creator_full_name: str
    max_players: int
    member_count: int
    is_active: bool
    created_at: datetime
    members: List[RoomMemberResponse] = []
    
    class Config:
        from_attributes = True

# API Endpoints
@app.get("/")
async def root():
    return {
        "message": "🏸 Badminton Rating API", 
        "version": "1.0.0",
        "status": "active"
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow()}

@app.post("/players/", response_model=PlayerResponse)
async def create_or_get_player(player: PlayerCreate, db: Session = Depends(get_db)):
    """Создает или получает игрока по telegram_id"""
    try:
        # Проверяем, существует ли игрок
        existing_player = db.query(Player).filter(Player.telegram_id == player.telegram_id).first()
        
        if existing_player:
            # Обновляем данные если они изменились
            existing_player.first_name = player.first_name
            if player.last_name:
                existing_player.last_name = player.last_name
            if player.username:
                existing_player.username = player.username
            db.commit()
            db.refresh(existing_player)
            return existing_player
        
        # Создаем нового игрока
        new_player = Player(**player.dict())
        db.add(new_player)
        db.commit()
        db.refresh(new_player)
        
        logger.info(f"✅ Создан новый игрок: {new_player.first_name} (ID: {new_player.telegram_id})")
        return new_player
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания игрока: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/players/{telegram_id}", response_model=PlayerResponse)
async def get_player(telegram_id: int, db: Session = Depends(get_db)):
    """Получает игрока по telegram_id"""
    player = db.query(Player).filter(Player.telegram_id == telegram_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Игрок не найден")
    return player

@app.post("/rooms/", response_model=RoomResponse)
async def create_room(room: RoomCreate, db: Session = Depends(get_db)):
    """Создает новую комнату"""
    try:
        # Находим игрока-создателя
        creator = db.query(Player).filter(Player.telegram_id == room.creator_telegram_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Создатель комнаты не найден")
        
        # Создаем комнату
        new_room = Room(
            name=room.name,
            creator_id=creator.id,
            max_players=room.max_players
        )
        db.add(new_room)
        db.commit()
        db.refresh(new_room)
        
        # Добавляем создателя как участника и лидера
        room_member = RoomMember(
            room_id=new_room.id,
            player_id=creator.id,
            is_leader=True
        )
        db.add(room_member)
        db.commit()
        
        # Формируем ответ
        creator_full_name = f"{creator.first_name} {creator.last_name or ''}".strip()
        
        result = RoomResponse(
            id=new_room.id,
            name=new_room.name,
            creator_id=new_room.creator_id,
            creator_full_name=creator_full_name,
            max_players=new_room.max_players,
            member_count=1,
            is_active=new_room.is_active,
            created_at=new_room.created_at,
            members=[RoomMemberResponse(
                id=room_member.id,
                player=creator,
                is_leader=True,
                joined_at=room_member.joined_at
            )]
        )
        
        logger.info(f"✅ Создана комната: {new_room.name} (ID: {new_room.id})")
        return result
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания комнаты: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/rooms/", response_model=List[RoomResponse])
async def get_rooms(db: Session = Depends(get_db)):
    """Получает список всех активных комнат"""
    try:
        rooms = db.query(Room).filter(Room.is_active == True).all()
        
        result = []
        for room in rooms:
            # Получаем всех участников комнаты
            members = db.query(RoomMember).filter(RoomMember.room_id == room.id).all()
            
            # Формируем полное имя создателя
            creator_full_name = f"{room.creator.first_name} {room.creator.last_name or ''}".strip()
            
            room_response = RoomResponse(
                id=room.id,
                name=room.name,
                creator_id=room.creator_id,
                creator_full_name=creator_full_name,
                max_players=room.max_players,
                member_count=len(members),
                is_active=room.is_active,
                created_at=room.created_at,
                members=[
                    RoomMemberResponse(
                        id=member.id,
                        player=member.player,
                        is_leader=member.is_leader,
                        joined_at=member.joined_at
                    ) for member in members
                ]
            )
            result.append(room_response)
        
        logger.info(f"✅ Найдено комнат: {len(result)}")
        return result
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения комнат: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/rooms/{room_id}", response_model=RoomResponse)
async def get_room(room_id: int, db: Session = Depends(get_db)):
    """Получает детали комнаты по ID"""
    try:
        room = db.query(Room).filter(Room.id == room_id).first()
        if not room:
            raise HTTPException(status_code=404, detail="Комната не найдена")
        
        # Получаем всех участников комнаты
        members = db.query(RoomMember).filter(RoomMember.room_id == room_id).all()
        
        # Формируем полное имя создателя
        creator_full_name = f"{room.creator.first_name} {room.creator.last_name or ''}".strip()
        
        result = RoomResponse(
            id=room.id,
            name=room.name,
            creator_id=room.creator_id,
            creator_full_name=creator_full_name,
            max_players=room.max_players,
            member_count=len(members),
            is_active=room.is_active,
            created_at=room.created_at,
            members=[
                RoomMemberResponse(
                    id=member.id,
                    player=member.player,
                    is_leader=member.is_leader,
                    joined_at=member.joined_at
                ) for member in members
            ]
        )
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения комнаты {room_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/rooms/{room_id}")
async def delete_room(room_id: int, db: Session = Depends(get_db)):
    """Удаляет комнату"""
    try:
        room = db.query(Room).filter(Room.id == room_id).first()
        if not room:
            raise HTTPException(status_code=404, detail="Комната не найдена")
        
        # Удаляем всех участников
        db.query(RoomMember).filter(RoomMember.room_id == room_id).delete()
        
        # Удаляем комнату
        db.delete(room)
        db.commit()
        
        logger.info(f"✅ Комната {room_id} удалена")
        return {"message": "Комната успешно удалена"}
        
    except Exception as e:
        logger.error(f"❌ Ошибка удаления комнаты {room_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Для совместимости с Vercel
def handler(request, context):
    return app(request, context)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
