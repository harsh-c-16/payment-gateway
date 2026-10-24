# Payments Service (M3)

**Owner:** Aditya Gaurav (B24CM1003)  
**Specification Brief:** [06_ADITYA_GAURAV.md](file:///c:/Users/voraj/OneDrive/Desktop/Studies/Sem5/DE/DE%20Project/payment-gateway/docs/specs/06_ADITYA_GAURAV.md)  
**Contract Authority:** [contracts/http/transactions.yaml](file:///c:/Users/voraj/OneDrive/Desktop/Studies/Sem5/DE/DE%20Project/payment-gateway/contracts/http/transactions.yaml) & [02_COMMON_SPEC.md §4](file:///c:/Users/voraj/OneDrive/Desktop/Studies/Sem5/DE/DE%20Project/payment-gateway/docs/specs/02_COMMON_SPEC.md#L127-L160)  
**Database:** `payments_db` (Isolated schema and write credentials)

## Scope
Maintains payment attempt records, simulated payment authorization/debit ledgers, reversals, and idempotency guarantees. Emits payment state transition events via the shared outbox.
