from datetime import datetime, timedelta
from dotenv import load_dotenv

# load variables from .env
load_dotenv()

from harmony import app
from harmony.analyzer import Analyzer


# analyzer = Analyzer('979554513021177909')
# print("starting analysis now")
# analyzer.start_analysis()
# TODO: get rid of this (its just for copy and paste into terminal for easy testing)
from harmony import db
from harmony.models import *
from harmony.analyzer import *
analyzer = Analyzer('979554513021177909')
db.drop_all()
db.create_all()
analyzer.start_analysis()