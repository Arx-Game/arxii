# Beat expiry is a completion, not a field flip

Beat expiry is a completion, not a field flip. Expiry fires the authored expired
pool, grades stakes LOSS, closes the contract and writes the ledger, through the
same tail every outcome uses; it awards no legend. Rejected: flipping the field
only (the authored branch was inert, #3558); a dedicated expiry resolver beside
the tail (a second completion path).

> Status: accepted · Source: #3558
