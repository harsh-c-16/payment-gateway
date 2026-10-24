# Inventory & Reservation Service (M3)

**Owner:** Aditya Gaurav (B24CM1003)  
**Specification Brief:** [06_ADITYA_GAURAV.md](file:///c:/Users/voraj/OneDrive/Desktop/Studies/Sem5/DE/DE%20Project/payment-gateway/docs/specs/06_ADITYA_GAURAV.md)  
**Contract Authority:** [contracts/http/transactions.yaml](file:///c:/Users/voraj/OneDrive/Desktop/Studies/Sem5/DE/DE%20Project/payment-gateway/contracts/http/transactions.yaml) & [02_COMMON_SPEC.md §4](file:///c:/Users/voraj/OneDrive/Desktop/Studies/Sem5/DE/DE%20Project/payment-gateway/docs/specs/02_COMMON_SPEC.md#L127-L160)  
**Database:** `inventory_db` (Isolated schema and write credentials)

## Scope
Maintains authoritative stock levels and serialized stock mutations. Handles reservations, expiry sweeps, and releases. Publishes inventory change events to Kafka via the shared outbox.
