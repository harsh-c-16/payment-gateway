# Analytical Compaction Engine (M2)

**Owner:** Harsh Chaudhari (B24CM1027)  
**Specification Brief:** [05_HARSH_CHAUDHARI.md](file:///c:/Users/voraj/OneDrive/Desktop/Studies/Sem5/DE/DE%20Project/payment-gateway/docs/specs/05_HARSH_CHAUDHARI.md)  
**Evaluation Reference:** [03_EVALUATION_SPEC.md §4](file:///c:/Users/voraj/OneDrive/Desktop/Studies/Sem5/DE/DE%20Project/payment-gateway/docs/specs/03_EVALUATION_SPEC.md)  

## Scope
Implements layout transforms and file-compaction strategies for Gold Parquet datasets (coalescing small files, z-order sorting, dictionary encoding). Emits candidate manifests for Vichitr (M4) to validate and publish.
