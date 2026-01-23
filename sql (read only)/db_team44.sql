DROP DATABASE IF EXISTS flytau;
CREATE DATABASE flytau;
USE flytau;
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'rootroot';
FLUSH PRIVILEGES;
-- =================================================
-- Manager / Pilot / FlightAttendant
-- =================================================
CREATE TABLE Manager (
    id INT NOT NULL,
    first_name_he VARCHAR(50),
    last_name_he VARCHAR(50),
    start_date DATE,
    city VARCHAR(100),
    street VARCHAR(100),
    house_number INT,
    password VARCHAR(20),
    PRIMARY KEY (id)
);

CREATE TABLE Pilot (
    id INT NOT NULL,
    first_name_he VARCHAR(50),
    last_name_he VARCHAR(50),
    start_date DATE,
    city VARCHAR(100),
    street VARCHAR(100),
    house_number INT,
    big_aircraft_cert TINYINT,
    PRIMARY KEY (id)
);

CREATE TABLE FlightAttendant (
    id INT NOT NULL,
    first_name_he VARCHAR(50),
    last_name_he VARCHAR(50),
    start_date DATE,
    city VARCHAR(100),
    street VARCHAR(100),
    house_number INT,
    big_aircraft_cert TINYINT,
    PRIMARY KEY (id)
);

-- =================================================
-- Aircraft
-- =================================================
CREATE TABLE Aircraft (
    aircraft_id INT NOT NULL,
    manufacturer VARCHAR(100),
    purchase_date DATE,
    aircraft_size VARCHAR(50),
    PRIMARY KEY (aircraft_id)
);

-- =================================================
-- Class
-- =================================================
CREATE TABLE Class (
    aircraft_id INT NOT NULL,
    class_type VARCHAR(50) NOT NULL,
    total_rows INT,
    total_columns INT,
    PRIMARY KEY (aircraft_id, class_type),
    FOREIGN KEY (aircraft_id) REFERENCES Aircraft(aircraft_id)
);

-- =================================================
-- Seat
-- =================================================
CREATE TABLE Seat (
    aircraft_id INT NOT NULL,
    class_type VARCHAR(50) NOT NULL,
    row_num INT NOT NULL,
    column_number INT NOT NULL,
    PRIMARY KEY (aircraft_id, class_type, row_num, column_number),
    FOREIGN KEY (aircraft_id, class_type)
        REFERENCES Class(aircraft_id, class_type)
);

-- =================================================
-- GuestUser
-- =================================================
CREATE TABLE GuestUser (
    email VARCHAR(255) NOT NULL,
    first_name_en VARCHAR(50),
    last_name_en VARCHAR(50),
    PRIMARY KEY (email)
);

CREATE TABLE GuestPhone (
    email VARCHAR(255) NOT NULL,
    phone_number VARCHAR(20) NOT NULL,
    PRIMARY KEY (email, phone_number),
    FOREIGN KEY (email) REFERENCES GuestUser(email)
);

-- =================================================
-- RegisteredUser
-- =================================================
CREATE TABLE RegisteredUser (
    email VARCHAR(255) NOT NULL,
    first_name_en VARCHAR(50),
    last_name_en VARCHAR(50),
    birth_date DATE,
    registration_date DATE,
    passport_number VARCHAR(20),
    password VARCHAR(20),
    PRIMARY KEY (email)
);

CREATE TABLE RegisteredPhone (
    email VARCHAR(255) NOT NULL,
    phone_number VARCHAR(20) NOT NULL,
    PRIMARY KEY (email, phone_number),
    FOREIGN KEY (email) REFERENCES RegisteredUser(email)
);

-- =================================================
-- FlightLength (הזזה לפני טבלת Flight כדי שהטריגר יוכל להסתמך עליה)
-- =================================================
CREATE TABLE FlightLength (
    origin VARCHAR(100) NOT NULL,
    destination VARCHAR(100) NOT NULL,
    length_minutes TIME,
    PRIMARY KEY (origin, destination)
);

-- =================================================
-- Flight
-- =================================================
CREATE TABLE Flight (
    flight_number INT NOT NULL,
    aircraft_id INT,
    origin VARCHAR(100),
    destination VARCHAR(100),
    departure_time DATETIME,
    arrival_time DATETIME DEFAULT NULL, -- שדה נגזר המאפשר NULL עבור הטריגר
    flight_status VARCHAR(50),
    PRIMARY KEY (flight_number),
    FOREIGN KEY (aircraft_id) REFERENCES Aircraft(aircraft_id)
);

-- =================================================
-- Trigger: Calculate Arrival Time
-- =================================================
DELIMITER //
CREATE TRIGGER before_flight_insert
BEFORE INSERT ON Flight
FOR EACH ROW
BEGIN
    DECLARE duration_val TIME;
    
    -- שליפת משך הטיסה מטבלת אורך טיסה לפי מוצא ויעד
    SELECT length_minutes INTO duration_val 
    FROM FlightLength 
    WHERE origin = NEW.origin AND destination = NEW.destination;
    
    -- עדכון זמן הנחיתה: המראה + משך
    IF duration_val IS NOT NULL THEN
        SET NEW.arrival_time = ADDTIME(NEW.departure_time, duration_val);
    END IF;
END;
//
DELIMITER ;

-- =================================================
-- Booking
-- =================================================
CREATE TABLE Booking (
    booking_id VARCHAR(6) NOT NULL,
    registered_email VARCHAR(255) NULL,
    guest_email VARCHAR(255),
    flight_number INT,
    price DECIMAL(10,2),
    booking_date DATE,
    booking_status VARCHAR(50),
    PRIMARY KEY (booking_id),
    FOREIGN KEY (registered_email) REFERENCES RegisteredUser(email),
    FOREIGN KEY (guest_email) REFERENCES GuestUser(email),
    FOREIGN KEY (flight_number) REFERENCES Flight(flight_number)
);

-- =================================================
-- Ticket
-- =================================================
CREATE TABLE Ticket (
    booking_id VARCHAR(6) NOT NULL,
    flight_number INT NOT NULL,
    aircraft_id INT NOT NULL,
    class_type VARCHAR(50) NOT NULL,
    row_num INT NOT NULL,
    column_number INT NOT NULL,
    PRIMARY KEY (
        booking_id,
        flight_number,
        aircraft_id,
        class_type,
        row_num,
        column_number
    ),
    FOREIGN KEY (booking_id) REFERENCES Booking(booking_id),
    FOREIGN KEY (flight_number) REFERENCES Flight(flight_number),
    FOREIGN KEY (aircraft_id, class_type, row_num, column_number)
        REFERENCES Seat(aircraft_id, class_type, row_num, column_number)
);

-- =================================================
-- FlightAttendants on flights
-- =================================================
CREATE TABLE FlightAttendants_on_Flights (
    id INT NOT NULL,
    flight_number INT NOT NULL,
    PRIMARY KEY (id, flight_number),
    FOREIGN KEY (id) REFERENCES FlightAttendant(id),
    FOREIGN KEY (flight_number) REFERENCES Flight(flight_number)
);

-- =================================================
-- Pilots on Flights
-- =================================================
CREATE TABLE Pilots_on_Flights (
    id INT NOT NULL,
    flight_number INT NOT NULL,
    PRIMARY KEY (id, flight_number),
    FOREIGN KEY (id) REFERENCES Pilot(id),
    FOREIGN KEY (flight_number) REFERENCES Flight(flight_number)
);

-- =================================================
-- Classes on Flights
-- =================================================
CREATE TABLE Classes_on_Flights (
    aircraft_id INT NOT NULL,
    class_type VARCHAR(50) NOT NULL,
    flight_number INT NOT NULL,
    class_price DECIMAL(10,2),
    PRIMARY KEY (aircraft_id, class_type, flight_number),
    FOREIGN KEY (aircraft_id, class_type)
        REFERENCES Class(aircraft_id, class_type),
    FOREIGN KEY (flight_number)
        REFERENCES Flight(flight_number)
);

-- =================================================
-- Seats on flights
-- =================================================
CREATE TABLE Seats_on_Flights (
    aircraft_id INT NOT NULL,
    class_type VARCHAR(50) NOT NULL,
    row_num INT NOT NULL,
    column_number INT NOT NULL,
    flight_number INT NOT NULL,
    available TINYINT,
    PRIMARY KEY (
        aircraft_id,
        class_type,
        row_num,
        column_number,
        flight_number
    ),
    FOREIGN KEY (aircraft_id, class_type, row_num, column_number)
        REFERENCES Seat(aircraft_id, class_type, row_num, column_number),
    FOREIGN KEY (flight_number)
        REFERENCES Flight(flight_number)
);

-- =================================================
-- Seats in Booking
-- =================================================
CREATE TABLE Seats_in_Booking (
    aircraft_id INT NOT NULL,
    class_type VARCHAR(50) NOT NULL,
    row_num INT NOT NULL,
    column_number INT NOT NULL,
    booking_id VARCHAR(6) NOT NULL,
    PRIMARY KEY (
        aircraft_id,
        class_type,
        row_num,
        column_number,
        booking_id
    ),
    FOREIGN KEY (aircraft_id, class_type, row_num, column_number)
        REFERENCES Seat(aircraft_id, class_type, row_num, column_number),
    FOREIGN KEY (booking_id)
        REFERENCES Booking(booking_id)
);