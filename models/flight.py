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
        """Fetch distinct origins/destinations for the search form."""
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT DISTINCT origin FROM Flight ORDER BY origin ASC")
            origins = cursor.fetchall()
            cursor.execute("SELECT DISTINCT destination FROM Flight ORDER BY destination ASC")
            destinations = cursor.fetchall()
            return origins, destinations

    @staticmethod
    def search(origin, destination):
        """Search only ACTIVE flights."""
        query = """
            SELECT *
            FROM Flight
            WHERE origin = %s
              AND destination = %s
              AND flight_status = 'Active'
            ORDER BY departure_time ASC
        """
        with DB.get_cursor() as cursor:
            cursor.execute(query, (origin, destination))
            return cursor.fetchall()

    @staticmethod
    def get_seat_map(flight_number: int):
        with DB.get_cursor() as cursor:
            cursor.execute(
                "SELECT aircraft_id FROM Flight WHERE flight_number = %s",
                (flight_number,)
            )
            f = cursor.fetchone()
            if not f:
                return []

            aircraft_id = f["aircraft_id"]

            query = """
                SELECT
                    s.row_num,
                    s.column_number,
                    s.class_type,
                    CASE
                        WHEN t.booking_id IS NULL THEN 1
                        ELSE 0
                    END AS available,
                    cof.class_price
                FROM Seat s
                LEFT JOIN Classes_on_Flights cof
                  ON cof.flight_number = %s
                 AND cof.class_type = s.class_type
                 AND cof.aircraft_id = s.aircraft_id
                LEFT JOIN Ticket t
                  ON t.flight_number = %s
                 AND t.class_type = s.class_type
                 AND t.row_num = s.row_num
                 AND t.column_number = s.column_number
                WHERE s.aircraft_id = %s
                ORDER BY
                    FIELD(s.class_type, 'First', 'Business', 'Economy'),
                    s.row_num,
                    s.column_number
            """
            cursor.execute(query, (flight_number, flight_number, aircraft_id))
            return cursor.fetchall()

    @staticmethod
    def update_status_if_full(flight_number: int):
        """
        If all seats are taken → update flight_status to 'Full'
        """
        with DB.get_cursor() as cursor:
            # total seats in aircraft
            cursor.execute("""
                    SELECT COUNT(*) AS total_seats
                    FROM Seat
                    WHERE aircraft_id = (
                        SELECT aircraft_id
                        FROM Flight
                        WHERE flight_number = %s
                    )
                """, (flight_number,))
            total_seats = cursor.fetchone()["total_seats"]

            # taken seats
            cursor.execute("""
                    SELECT COUNT(*) AS taken_seats
                    FROM Ticket
                    WHERE flight_number = %s
                """, (flight_number,))
            taken_seats = cursor.fetchone()["taken_seats"]

            if total_seats > 0 and total_seats == taken_seats:
                cursor.execute("""
                        UPDATE Flight
                        SET flight_status = 'Full'
                        WHERE flight_number = %s
                    """, (flight_number,))