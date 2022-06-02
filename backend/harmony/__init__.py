from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
db = SQLAlchemy(app)

from harmony import routes
from harmony import models

# TODO: create tables if they dont already exist
# db.drop_all()
# db.create_all()
# db.session.commit()