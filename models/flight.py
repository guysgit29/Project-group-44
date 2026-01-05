from database import DB

class Flight:
    def __init__(self, flight_number, aircraft_id, origin, destination, departure, arrival, status):
        self.flight_number = flight_number
        self.aircraft_id = aircraft_id
        self.origin = origin
        self.destination = destination
        self.departure = departure
        self.arrival = arrival
        self.status = status

    @staticmethod
    def get_all_origins_and_destinations():
        """Fetches distinct origins and destinations for search forms"""
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT DISTINCT origin FROM Flight ORDER BY origin ASC")
            origins = cursor.fetchall()
            cursor.execute("SELECT DISTINCT destination FROM Flight ORDER BY destination ASC")
            destinations = cursor.fetchall()
            return origins, destinations

    @staticmethod
    def search(origin, destination):
        """Searches for flights based on user input"""
        query = "SELECT * FROM Flight WHERE origin = %s AND destination = %s ORDER BY departure_time ASC"
        with DB.get_cursor() as cursor:
            cursor.execute(query, (origin, destination))
            return cursor.fetchall()