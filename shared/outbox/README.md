# Shared Transactional Outbox Library (M3)

**Owner:** Aditya Gaurav (B24CM1003)  
**Specification Brief:** [06_ADITYA_GAURAV.md](file:///c:/Users/voraj/OneDrive/Desktop/Studies/Sem5/DE/DE%20Project/payment-gateway/docs/specs/06_ADITYA_GAURAV.md)  
**Contract Authority:** [02_COMMON_SPEC.md §7](file:///c:/Users/voraj/OneDrive/Desktop/Studies/Sem5/DE/DE%20Project/payment-gateway/docs/specs/02_COMMON_SPEC.md)  

## Scope
Provides a reusable library for appending events to service-local outbox tables in the same PostgreSQL transaction as domain mutations. Implements a restart-safe background relay to Kafka using Vichitr's event transport SDK.
