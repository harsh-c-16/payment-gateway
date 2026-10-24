# Streaming Ingestion & Bronze Landing (M4)

**Owner:** Vichitr Arora (B24CM1067)  
**Specification Brief:** [07_VICHITR_ARORA.md](file:///c:/Users/voraj/OneDrive/Desktop/Studies/Sem5/DE/DE%20Project/payment-gateway/docs/specs/07_VICHITR_ARORA.md)  
**Contract Authority:** [02_COMMON_SPEC.md §8](file:///c:/Users/voraj/OneDrive/Desktop/Studies/Sem5/DE/DE%20Project/payment-gateway/docs/specs/02_COMMON_SPEC.md) & [contracts/events/](file:///c:/Users/voraj/OneDrive/Desktop/Studies/Sem5/DE/DE%20Project/payment-gateway/contracts/events/)  

## Scope
Consumes raw event envelopes from the five Kafka topics, validates against Confluent Schema Registry schemas, handles deduplication, and lands append-only raw events into Bronze storage.
