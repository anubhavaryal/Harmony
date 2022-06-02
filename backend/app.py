from datetime import datetime, timedelta
from dotenv import load_dotenv

# load variables from .env
load_dotenv()

from harmony import app
from harmony.analyzer import Analyzer


analyzer = Analyzer('979554513021177909')
print("starting analysis now")
analyzer.start_analysis()