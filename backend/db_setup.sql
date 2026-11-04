-- Run this in MySQL Workbench (File > New Query Tab), connected as root or an admin user.

CREATE DATABASE IF NOT EXISTS uphsl_scheduling
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- Dedicated app user instead of using root from Django — safer, and easy to rotate later.
CREATE USER IF NOT EXISTS 'uphsl_app'@'localhost' IDENTIFIED BY 'ChangeThisPassword123!';
GRANT ALL PRIVILEGES ON uphsl_scheduling.* TO 'uphsl_app'@'localhost';
FLUSH PRIVILEGES;

-- Sanity check: should list the empty new database.
SHOW DATABASES LIKE 'uphsl_scheduling';
