# Lakehouse Storage & Active Manifests (M4)

**Owner:** Vichitr Arora (B24CM1067)  
**Specification Brief:** [07_VICHITR_ARORA.md](file:///c:/Users/voraj/OneDrive/Desktop/Studies/Sem5/DE/DE%20Project/payment-gateway/docs/specs/07_VICHITR_ARORA.md)  
**Contract Authority:** [02_COMMON_SPEC.md §8](file:///c:/Users/voraj/OneDrive/Desktop/Studies/Sem5/DE/DE%20Project/payment-gateway/docs/specs/02_COMMON_SPEC.md)  

## Scope
Manages the durable local-volume file store for Bronze/Silver/Gold files and the atomic active manifest pointer (`DatasetManifest`). Validates and publishes compactor candidates produced by M2.
