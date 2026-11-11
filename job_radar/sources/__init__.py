"""The job boards: one adapter per source into the common `Posting` format.

`base` holds the interfaces every board implements; `getro` (Fast Forward),
`jobspipe` and `demo` are the boards, and `board_client` the HTTP client they share.
"""
