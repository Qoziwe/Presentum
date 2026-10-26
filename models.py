import os
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Slide(db.Model):
    __tablename__ = "slides"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    order_index = db.Column(db.Integer, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "filename": self.filename,
            "url": f"/static/uploads/slides/{self.filename}",
            "order_index": self.order_index,
            "original_filename": self.original_filename
        }

class PresentationState(db.Model):
    __tablename__ = "presentation_state"

    id = db.Column(db.Integer, primary_key=True)
    current_slide_index = db.Column(db.Integer, default=1, nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    @classmethod
    def get_current(cls):
        state = cls.query.filter_by(id=1).first()
        if not state:
            state = cls(id=1, current_slide_index=1)
            db.session.add(state)
            db.session.commit()
        return state

    @classmethod
    def set_current_index(cls, new_index):
        state = cls.get_current()
        state.current_slide_index = new_index
        db.session.commit()
        return state
