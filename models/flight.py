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
        """Searches only for ACTIVE flights based on origin and destination"""
        # הוספנו תנאי שמסנן רק טיסות פעילות
        query = """
            SELECT * FROM Flight 
            WHERE origin = %s AND destination = %s AND flight_status = 'Active' 
            ORDER BY departure_time ASC
        """
        with DB.get_cursor() as cursor:
            cursor.execute(query, (origin, destination))
            return cursor.fetchall()

    @staticmethod
    def get_seat_map(flight_number):
        """Fetches seat map, classes, and prices for a flight"""
        # שים לב: אם ב-DB שלך העמודה נקראת seat_number, החלף את seat_id בהתאם
        query = """
            SELECT s.seat_number, s.class_name, s.base_price,
                   (SELECT COUNT(*) FROM Ticket t 
                    WHERE t.flight_number = %s AND t.seat_number = s.seat_number) as is_taken
            FROM Seat s
            JOIN Flight f ON f.aircraft_id = s.aircraft_id
            WHERE f.flight_number = %s
            ORDER BY s.seat_number ASC
        """
        with DB.get_cursor() as cursor:
            cursor.execute(query, (flight_number, flight_number))
            return cursor.fetchall()