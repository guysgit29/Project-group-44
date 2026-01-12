# ================================
# models/flight.py  (רק מה שצריך לשינוי)
# ================================
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

    # -------------------------
    # Customer helpers
    # -------------------------

    @staticmethod
    def get_all_origins_and_destinations():
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT DISTINCT origin FROM Flight ORDER BY origin ASC")
            origins = cursor.fetchall()

            cursor.execute("SELECT DISTINCT destination FROM Flight ORDER BY destination ASC")
            destinations = cursor.fetchall()

            return origins, destinations

    @staticmethod
    def sync_completed_flights() -> int:
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
                (int(flight_number),)
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
            cursor.execute(query, (int(flight_number), int(flight_number), aircraft_id))
            return cursor.fetchall()

    @staticmethod
    def update_status_by_capacity(flight_number: int) -> str | None:
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

    # -------------------------
    # Manager helpers
    # -------------------------

    @staticmethod
    def list_for_manager(selected_status: str = "", aircraft_id: int | None = None):
        query = """
            SELECT
                flight_number,
                aircraft_id,
                origin,
                destination,
                departure_time,
                arrival_time,
                flight_status
            FROM Flight
        """

        where = []
        params = []

        selected_status = (selected_status or "").strip()
        if selected_status:
            where.append("flight_status = %s")
            params.append(selected_status)

        if aircraft_id is not None:
            where.append("aircraft_id = %s")
            params.append(int(aircraft_id))

        if where:
            query += " WHERE " + " AND ".join(where)

        query += " ORDER BY departure_time DESC"

        with DB.get_cursor() as cursor:
            cursor.execute(query, tuple(params))
            return cursor.fetchall()

    @staticmethod
    def get_by_number(flight_number: int):
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT
                    flight_number,
                    aircraft_id,
                    origin,
                    destination,
                    departure_time,
                    arrival_time,
                    flight_status
                FROM Flight
                WHERE flight_number = %s
            """, (int(flight_number),))
            return cursor.fetchone()

    @staticmethod
    @staticmethod
    def get_all_aircraft_ids():
        """מחזיר רשימת מספרי מטוסים שקיימים בטיסות (ל-drop-down)."""
        with DB.get_cursor() as cursor:
            cursor.execute("""
                   SELECT DISTINCT aircraft_id
                   FROM Flight
                   WHERE aircraft_id IS NOT NULL
                   ORDER BY aircraft_id ASC
               """)
            rows = cursor.fetchall() or []
        return [r["aircraft_id"] for r in rows]
    @staticmethod
    def get_aircraft_size_for_flight(flight_number: int) -> str | None:
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT a.aircraft_size
                FROM Flight f
                JOIN Aircraft a ON a.aircraft_id = f.aircraft_id
                WHERE f.flight_number = %s
            """, (int(flight_number),))
            row = cursor.fetchone()
            return row.get("aircraft_size") if row else None

    @staticmethod
    def get_flight_window(flight_number: int):
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT
                    f.departure_time AS start_time,
                    COALESCE(
                        f.arrival_time,
                        ADDTIME(f.departure_time, fl.length_minutes)
                    ) AS end_time
                FROM Flight f
                LEFT JOIN FlightLength fl
                    ON fl.origin = f.origin AND fl.destination = f.destination
                WHERE f.flight_number = %s
            """, (int(flight_number),))
            row = cursor.fetchone()

        if not row:
            return None, None

        return row.get("start_time"), row.get("end_time")

    # -------------------------
    # Crew capacity rules (NO buffer)
    # -------------------------

    @staticmethod
    def get_required_crew_counts(flight_number: int) -> dict:
        size = (Flight.get_aircraft_size_for_flight(flight_number) or "").strip().lower()
        if size == "large":
            return {"pilots": 3, "attendants": 6}
        return {"pilots": 2, "attendants": 3}

    @staticmethod
    def count_assigned_pilots(flight_number: int) -> int:
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS c FROM pilots_on_flights WHERE flight_number=%s", (int(flight_number),))
            row = cursor.fetchone() or {}
        return int(row.get("c") or 0)

    @staticmethod
    def count_assigned_attendants(flight_number: int) -> int:
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS c FROM flightattendants_on_flights WHERE flight_number=%s", (int(flight_number),))
            row = cursor.fetchone() or {}
        return int(row.get("c") or 0)
