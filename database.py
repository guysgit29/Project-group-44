import mysql.connector
from contextlib import contextmanager


class DB:
    """
    Simple MySQL helper for FlyTAU.
    Usage:
        with DB.get_cursor() as cursor:
            cursor.execute(...)
            rows = cursor.fetchall()
    """

    HOST = "localhost"
    USER = "root"
    PASSWORD = "rootroot"
    DATABASE = "flytau"
    AUTH_PLUGIN = "mysql_native_password"

    @staticmethod
    def get_connection():
        """
        Creates and returns a new MySQL connection.
        autocommit=True so INSERT/UPDATE/DELETE are persisted immediately.
        """
        return mysql.connector.connect(
            host=DB.HOST,
            user=DB.USER,
            password=DB.PASSWORD,
            database=DB.DATABASE,
            autocommit=True,
            auth_plugin=DB.AUTH_PLUGIN,
        )

    @staticmethod
    @contextmanager
    def get_cursor(dictionary: bool = True):
        """
        Context manager that yields a cursor and closes cursor+connection safely.
        """
        mydb = None
        cursor = None
        try:
            mydb = DB.get_connection()
            cursor = mydb.cursor(dictionary=dictionary)
            yield cursor
        except mysql.connector.Error as err:
            print(f"Database connection error: {err}")
            raise
        finally:
            try:
                if cursor:
                    cursor.close()
            finally:
                if mydb:
                    mydb.close()