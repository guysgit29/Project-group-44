from flask import Flask, render_template, request, redirect, session
from utils import get_hall_dimensions, get_occupied_seats, save_booking
from flask_session import Session
from datetime import timedelta, date

app = Flask(__name__)

app.config.update(
    SESSION_TYPE="filesystem",
    SESSION_FILE_DIR="/flask_session_data",
    SESSION_PERMANENT=True,
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=10),
    SESSION_REFRESH_EACH_REQUEST=True,
    SESSION_COOKIE_SECURE=True
)

Session(app)

