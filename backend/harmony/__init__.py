from celery import Celery
from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event


# load variables from .env
load_dotenv()

app = Flask(__name__)
CORS(app)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# enable foreign key support if using sqlite
if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']:
    def enable_fk(dbapi_con, _):
        dbapi_con.execute('PRAGMA foreign_keys=ON')
    
    with app.app_context():
        from sqlalchemy import event
        event.listen(db.engine, 'connect', enable_fk)

celery = Celery('harmony', broker='amqp://', include=['harmony.tasks'])

from harmony import routes
# from harmony import models
# celery -A harmony.celery worker -l INFO
# celery -A harmony.celery purge
# sudo rabbitmq-server
# sudo rabbitmqctl stop