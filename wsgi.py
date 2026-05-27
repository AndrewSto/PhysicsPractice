import sys
import os

# ⚠️ Sostituisci TUOUSERNAME con il tuo username PythonAnywhere
path = '/home/TUOUSERNAME'
if path not in sys.path:
    sys.path.append(path)

# Credenziali Supabase
os.environ['DB_HOST'] = 'aws-0-eu-west-3.pooler.supabase.com'
os.environ['DB_PORT'] = '5432'
os.environ['DB_NAME'] = 'postgres'
os.environ['DB_USER'] = 'postgres.klmrtwkpizbakftttzxa'
os.environ['DB_PASSWORD'] = 'TUAPASSWORD'  # ⚠️ Sostituisci con la tua password
os.environ['SECRET_KEY'] = 'scegli-una-chiave-segreta-lunga-e-casuale'

from app import app as application
