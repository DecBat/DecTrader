"""
Shared logging utility.

Build a get_logger(name) function that:
  - Sets level to INFO
  - Writes to both console and logs/YYYY-MM-DD.log
  - Avoids duplicate handlers on re-import
"""
