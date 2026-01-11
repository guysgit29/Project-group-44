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
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT DISTINCT origin FROM Flight ORDER BY origin ASC")
            origins = cursor.fetchall()

            cursor.execute("SELECT DISTINCT destination FROM Flight ORDER BY destination ASC")
            destinations = cursor.fetchall()

            return origins, destinations

    # ------------------------------------------------------------
    # NEW: mark flights as Completed when arrival_time has passed
    # ------------------------------------------------------------
    @staticmethod
    def sync_completed_flights() -> int:
        """
        Sets Flight.flight_status = 'Completed' for flights that already landed.
        Works only for rows where arrival_time IS NOT NULL.
        Returns number of rows updated.
        """
        with DB.get_cursor() as cursor:
            cursor.execute("""
                UPDATE Flight
                SET flight_status = 'Completed'
                WHERE arrival_time IS NOT NULL
                  AND arrival_time < NOW()
                  AND flight_status <> 'Completed'
            """)
            return cursor.rowcount

    @staticmethod
    def search(origin, destination):
        """
        Search flights for customers:
        show only flights that are not Completed and not Full.
        (Usually you want only bookable flights)
        """
        # לפני חיפוש אפשר לסנכרן טיסות שנחתו (לא חובה, אבל מומלץ)
        Flight.sync_completed_flights()

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

    # ------------------------------------------------------------
    # Flight capacity status updater (Full <-> Active)
    # ------------------------------------------------------------
    @staticmethod
    def update_status_by_capacity(flight_number: int) -> str | None:
        """
        Sets Flight.flight_status to:
          - 'Full'   if sold seats == total seats
          - 'Active' if there is at least 1 free seat

        IMPORTANT:
        If the flight already Completed, we do NOT change it back.
        """
        if not flight_number:
            return None

        with DB.get_cursor() as cursor:
            cursor.execute(
                "SELECT aircraft_id, flight_status FROM Flight WHERE flight_number = %s",
                (int(flight_number),)
            )
            f = cursor.fetchone()
            if not f or f.get("aircraft_id") is None:
                return None

            current_status = (f.get("flight_status") or "").strip()

            # אם כבר נחתה/Completed — לא נוגעים
            if current_status == "Completed":
                return "Completed"

            aircraft_id = int(f["aircraft_id"])

            cursor.execute(
                "SELECT COUNT(*) AS total_seats FROM Seat WHERE aircraft_id = %s",
                (aircraft_id,)
            )
            total = int((cursor.fetchone() or {}).get("total_seats") or 0)

            cursor.execute(
                "SELECT COUNT(*) AS sold_seats FROM Ticket WHERE flight_number = %s",
                (int(flight_number),)
            )
            sold = int((cursor.fetchone() or {}).get("sold_seats") or 0)

            new_status = "Full" if total > 0 and sold >= total else "Active"

            if current_status != new_status:
                cursor.execute(
                    "UPDATE Flight SET flight_status = %s WHERE flight_number = %s",
                    (new_status, int(flight_number))
                )

            return new_status
