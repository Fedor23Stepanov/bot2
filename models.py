# models.py

from sqlalchemy import (
    Column, Integer, String, DateTime, Enum as SQLEnum, Boolean, ForeignKey, JSON
)
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    # Внутренний автоинкрементный PK
    id = Column(Integer, primary_key=True, autoincrement=True)
    # Реальный Telegram ID пользователя
    user_id = Column(Integer, unique=True, nullable=True, index=True)
    username = Column(String, nullable=False, unique=True)
    role = Column(SQLEnum("admin", "moderator", "user", name="user_roles"), nullable=False)
    status = Column(SQLEnum("activ", "pending", name="user_statuses"), nullable=False)
    transition_mode = Column(SQLEnum("immediate", "daily", name="transition_modes"), nullable=False, default="immediate")
    invited_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    created_date = Column(DateTime(timezone=True), server_default=func.now())
    activated_date = Column(DateTime(timezone=True), nullable=True)

    # Отношение пригласивший ↔ приглашенные
    inviter = relationship(
        "User",
        remote_side=[user_id],
        backref="invitees"
    )

class DeviceOption(Base):
    __tablename__ = "device_options"
    id        = Column(Integer, primary_key=True)
    ua        = Column(String, nullable=False)
    css_size  = Column(JSON, nullable=False)  # [width, height]
    platform  = Column(String, nullable=False)
    dpr       = Column(Integer, nullable=False)
    mobile    = Column(Boolean, nullable=False)
    model     = Column(String, nullable=True)

class ProxyLog(Base):
    __tablename__ = "proxy_logs"
    id        = Column(String, primary_key=True)  # UUID группы попыток
    attempt   = Column(Integer, primary_key=True)
    ip        = Column(String, nullable=True)
    city      = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

class Event(Base):
    __tablename__ = "events"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    user_id          = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    device_option_id = Column(Integer, ForeignKey("device_options.id"), nullable=True)
    state            = Column(SQLEnum(
                          "no_link",
                          "many_links",
                          "proxy_error",
                          "redirector_error",
                          "success",
                          name="event_states"
                       ), nullable=False)
    proxy_id         = Column(String, ForeignKey("proxy_logs.id"), nullable=True)
    initial_url      = Column(String, nullable=True)
    final_url        = Column(String, nullable=True)
    ip               = Column(String, nullable=True)
    isp              = Column(String, nullable=True)
    timestamp        = Column(DateTime(timezone=True), server_default=func.now())

class Queue(Base):
    __tablename__ = "queue"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    # Telegram ID пользователя, FK на users.user_id
    user_id         = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    message_id      = Column(Integer, nullable=False)
    url             = Column(String, nullable=False)
    transition_time = Column(DateTime(timezone=True), nullable=True)
    # Новый статус обработки: pending, in_progress, done
    status          = Column(SQLEnum("pending", "in_progress", "done", name="queue_statuses"), nullable=False, server_default="pending")
