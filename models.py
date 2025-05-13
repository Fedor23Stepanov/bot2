#models.py

from sqlalchemy import (
    Column, Integer, String, DateTime, Enum, Boolean, ForeignKey, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    user_id        = Column(Integer, primary_key=True)
    username       = Column(String, nullable=False, unique=True)
    role           = Column(Enum("admin","moderator","user"), nullable=False)
    status         = Column(Enum("activ","pending"), nullable=False)
    notify_mode    = Column(Enum("each","summary","none"), nullable=False, default="none")
    transition_mode= Column(Enum("immediate","daily"), nullable=False, default="immediate")
    invited_by     = Column(String, nullable=True)
    created_date   = Column(DateTime(timezone=True), server_default=func.now())
    activated_date = Column(DateTime(timezone=True), nullable=True)

class DeviceOption(Base):
    __tablename__ = "device_options"
    id        = Column(Integer, primary_key=True)
    ua        = Column(String, nullable=False)
    css_size  = Column(JSON, nullable=False)
    platform  = Column(String, nullable=False)
    dpr       = Column(Integer, nullable=False)
    mobile    = Column(Boolean, nullable=False)
    model     = Column(String, nullable=True)

class ProxyLog(Base):
    __tablename__ = "proxy_logs"
    id        = Column(String, primary_key=True)  # группа попыток: UUID
    attempt   = Column(Integer, primary_key=True)
    ip        = Column(String, nullable=True)
    city      = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

class Event(Base):
    __tablename__ = "events"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    user_id          = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    device_option_id = Column(Integer, ForeignKey("device_options.id"), nullable=True)
    state            = Column(Enum("no_link","many_links","proxy_error","redirector_error","success"), nullable=False)
    proxy_id         = Column(String, ForeignKey("proxy_logs.id"), nullable=True)
    initial_url      = Column(String, nullable=True)
    final_url        = Column(String, nullable=True)
    ip               = Column(String, nullable=True)
    isp              = Column(String, nullable=True)
    timestamp        = Column(DateTime(timezone=True), server_default=func.now())

class Queue(Base):
    __tablename__ = "queue"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    user_id         = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    message_id      = Column(Integer, nullable=False)
    url             = Column(String, nullable=False)
    transition_time = Column(DateTime(timezone=True), nullable=True)
