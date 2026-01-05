import mysql.connector
from contextlib import contextmanager

class DB:
    @staticmethod
    @contextmanager
    def get_cursor():
        mydb = None
        cursor = None
        try:
            mydb = mysql.connector.connect(
                host="localhost",
                user="root",
                password="rootroot",
                database="flytau",
                autocommit=True,
                auth_plugin='mysql_native_password'
            )
            cursor = mydb.cursor(dictionary=True)
            yield cursor
        except mysql.connector.Error as err:
            print(f"Database connection error: {err}")
            raise err
        finally:
            if cursor: cursor.close()
            if mydb: mydb.close()