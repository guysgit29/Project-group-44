import mysql.connector
from contextlib import contextmanager

class DBManager:
    @staticmethod
    @contextmanager
    def get_cursor():
        # הגדרות החיבור שלך - שנה כאן פעם אחת וזה יתעדכן בכל הפרויקט
        config = {
            'host': "localhost",
            'user': "root",
            'password': "rootroot",
            'database': "flytau",
            'autocommit': True
        }
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor(dictionary=True) # מחזיר תוצאות כמילון
        try:
            yield cursor
        finally:
            cursor.close()
            conn.close()