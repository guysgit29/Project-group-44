from database import DB
class Aircraft:
    """Manages aircraft records plus related classes/seats creation and UI data retrieval."""
    MANUFACTURERS = ["Boeing", "Airbus", "Dassault"]
    ALLOWED_SIZES = {"Large", "Small"}
    def __init__(self, aircraft_id, manufacturer, size):
        self.id = aircraft_id
        self.manufacturer = manufacturer
        self.size = size  # Large or Small

    @staticmethod
    def get_by_id(aircraft_id):  # Fetch one aircraft by id (returns Aircraft object or None)
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT * FROM Aircraft WHERE aircraft_id = %s", (aircraft_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return Aircraft(row["aircraft_id"], row["manufacturer"], row["aircraft_size"])

    @staticmethod
    def get_all():  # Fetch all aircraft rows for listing screens
        with DB.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT aircraft_id, manufacturer, purchase_date, aircraft_size
                FROM Aircraft
                ORDER BY aircraft_id DESC
                """
            )
            return cursor.fetchall() or []

    @staticmethod
    def get_filtered(aircraft_id=None, manufacturer=None, size=None):  # Fetch aircraft rows filtered by optional id/manufacturer/size
        query = """
            SELECT aircraft_id, manufacturer, purchase_date, aircraft_size
            FROM Aircraft
            WHERE 1=1
        """
        params = []
        if aircraft_id:
            query += " AND aircraft_id LIKE %s"
            params.append(f"%{aircraft_id}%")
        if manufacturer:
            query += " AND manufacturer = %s"
            params.append(manufacturer)
        if size:
            query += " AND aircraft_size = %s"
            params.append(size)
        query += " ORDER BY aircraft_id DESC"
        with DB.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall() or []

    @staticmethod
    def get_next_aircraft_id() -> int:  # Generate next aircraft_id using MAX+1
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT COALESCE(MAX(aircraft_id), 100) AS max_id FROM Aircraft")
            row = cursor.fetchone() or {}
            return int(row.get("max_id") or 100) + 1

    @staticmethod
    def _group_rows_by_aircraft_id(rows):  # Group DB rows into a dict: {aircraft_id: [rows]}
        result = {}
        for r in rows or []:
            aid = int(r["aircraft_id"])
            result.setdefault(aid, []).append(r)
        return result

    @staticmethod
    def get_classes_for_aircrafts(aircraft_ids):  # Get seat-layout and seat-count per class for multiple aircrafts
        if not aircraft_ids:
            return {}
        placeholders = ",".join(["%s"] * len(aircraft_ids))
        with DB.get_cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    C.aircraft_id,
                    C.class_type,
                    C.total_rows,
                    C.total_columns,
                    COUNT(S.row_num) AS seats_count
                FROM Class C
                LEFT JOIN Seat S
                  ON S.aircraft_id = C.aircraft_id
                 AND S.class_type = C.class_type
                WHERE C.aircraft_id IN ({placeholders})
                GROUP BY C.aircraft_id, C.class_type, C.total_rows, C.total_columns
                ORDER BY C.aircraft_id DESC, C.class_type
                """,
                tuple(aircraft_ids),
            )
            rows = cursor.fetchall() or []
        return Aircraft._group_rows_by_aircraft_id(rows)

    @staticmethod
    def get_flights_for_aircrafts(aircraft_ids):  # Get flight history for multiple aircrafts
        if not aircraft_ids:
            return {}
        placeholders = ",".join(["%s"] * len(aircraft_ids))
        with DB.get_cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    aircraft_id,
                    flight_number,
                    origin,
                    destination,
                    departure_time,
                    arrival_time,
                    flight_status
                FROM Flight
                WHERE aircraft_id IN ({placeholders})
                ORDER BY aircraft_id DESC, departure_time DESC
                """,
                tuple(aircraft_ids),
            )
            rows = cursor.fetchall() or []
        return Aircraft._group_rows_by_aircraft_id(rows)

    @staticmethod
    def get_flights_history_for_aircrafts(aircraft_ids):  # Compatibility wrapper for older route/model usage
        return Aircraft.get_flights_for_aircrafts(aircraft_ids)

    @staticmethod
    def _insert_class_and_seats(cursor, aircraft_id: int, class_type: str, total_rows: int, total_cols: int):  # Insert a class row and generate all seat rows for that class layout
        cursor.execute(
            """
            INSERT INTO Class (aircraft_id, class_type, total_rows, total_columns)
            VALUES (%s, %s, %s, %s)
            """,
            (aircraft_id, class_type, int(total_rows), int(total_cols)),
        )
        for r in range(1, int(total_rows) + 1):
            for c in range(1, int(total_cols) + 1):
                cursor.execute(
                    """
                    INSERT INTO Seat (aircraft_id, class_type, row_num, column_number)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (aircraft_id, class_type, r, c),
                )

    @staticmethod
    def create_aircraft_with_seats(
        manufacturer: str,
        purchase_date: str,
        economy_rows: int,
        economy_cols: int,
        business_rows: int | None,
        business_cols: int | None,
    ) -> int:  # Create an aircraft and auto-generate its classes and seats
        aircraft_id = Aircraft.get_next_aircraft_id()
        has_business = (
            business_rows is not None
            and business_cols is not None
            and int(business_rows) > 0
            and int(business_cols) > 0
        )
        aircraft_size = "Large" if has_business else "Small"
        with DB.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO Aircraft (aircraft_id, manufacturer, purchase_date, aircraft_size)
                VALUES (%s, %s, %s, %s)
                """,
                (aircraft_id, manufacturer, purchase_date, aircraft_size),
            )
            Aircraft._insert_class_and_seats(cursor, aircraft_id, "Economy", int(economy_rows), int(economy_cols))
            if has_business:
                Aircraft._insert_class_and_seats(cursor, aircraft_id, "Business", int(business_rows), int(business_cols))
        return aircraft_id

    @staticmethod
    def parse_filters(args) -> dict:  # Normalize UI query-string filters into a clean dict
        aircraft_id = (args.get("aircraft_id") or "").strip()
        manufacturer = (args.get("manufacturer") or "").strip()
        size = (args.get("size") or "").strip()
        if manufacturer not in Aircraft.MANUFACTURERS:
            manufacturer = ""
        if size and size not in Aircraft.ALLOWED_SIZES:
            size = ""
        return {"aircraft_id": aircraft_id, "manufacturer": manufacturer, "size": size}

    @staticmethod
    def list_page_data(filters: dict):  # Build the full dataset needed for the aircraft listing page
        aircrafts = Aircraft.get_filtered(
            aircraft_id=filters.get("aircraft_id") or None,
            manufacturer=filters.get("manufacturer") or None,
            size=filters.get("size") or None,
        )
        aircraft_ids = [int(a["aircraft_id"]) for a in aircrafts] if aircrafts else []
        classes_map = Aircraft.get_classes_for_aircrafts(aircraft_ids)
        flights_map = Aircraft.get_flights_for_aircrafts(aircraft_ids)
        return aircrafts, classes_map, flights_map

    @staticmethod
    def build_pending_from_form(form) -> tuple[dict | None, str | None]:  # Validate the create-aircraft form and return a session-ready pending dict
        manufacturer = (form.get("manufacturer") or "").strip()
        purchase_date = (form.get("purchase_date") or "").strip()
        econ_rows = (form.get("economy_rows") or "").strip()
        econ_cols = (form.get("economy_cols") or "").strip()
        biz_rows = (form.get("business_rows") or "").strip()
        biz_cols = (form.get("business_cols") or "").strip()
        if manufacturer not in Aircraft.MANUFACTURERS:
            return None, "יצרן לא תקין"
        if not purchase_date:
            return None, "חובה לבחור תאריך רכישה"
        if not econ_rows.isdigit() or int(econ_rows) <= 0:
            return None, "מספר שורות באקונומי חייב להיות מספר חיובי"
        if not econ_cols.isdigit() or int(econ_cols) <= 0:
            return None, "מספר עמודות באקונומי חייב להיות מספר חיובי"
        business_rows_val = None
        business_cols_val = None
        if biz_rows or biz_cols:
            if (not biz_rows.isdigit()) or (not biz_cols.isdigit()) or int(biz_rows) <= 0 or int(biz_cols) <= 0:
                return None, "אם ממלאים עסקים – חייבים גם שורות וגם עמודות במספר חיובי"
            business_rows_val = int(biz_rows)
            business_cols_val = int(biz_cols)
        next_id = Aircraft.get_next_aircraft_id()
        size = "Large" if (business_rows_val and business_cols_val) else "Small"
        pending = {
            "aircraft_id": next_id,
            "manufacturer": manufacturer,
            "purchase_date": purchase_date,
            "aircraft_size": size,
            "economy_rows": int(econ_rows),
            "economy_cols": int(econ_cols),
            "business_rows": business_rows_val,
            "business_cols": business_cols_val,
        }
        return pending, None

    @staticmethod
    def create_from_pending(pending: dict) -> int:  # Create a new aircraft from a validated pending dict
        return Aircraft.create_aircraft_with_seats(
            manufacturer=pending["manufacturer"],
            purchase_date=pending["purchase_date"],
            economy_rows=int(pending["economy_rows"]),
            economy_cols=int(pending["economy_cols"]),
            business_rows=pending.get("business_rows"),
            business_cols=pending.get("business_cols"),
        )
