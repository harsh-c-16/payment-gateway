# Catalog & Retrieval Service (M2)

**Owner:** Harsh Chaudhari (B24CM1027)  
**Specification Brief:** [05_HARSH_CHAUDHARI.md](file:///c:/Users/voraj/OneDrive/Desktop/Studies/Sem5/DE/DE%20Project/payment-gateway/docs/specs/05_HARSH_CHAUDHARI.md)  
**Contract Authority:** [contracts/http/catalog.yaml](file:///c:/Users/voraj/OneDrive/Desktop/Studies/Sem5/DE/DE%20Project/payment-gateway/contracts/http/catalog.yaml) & [02_COMMON_SPEC.md §4](file:///c:/Users/voraj/OneDrive/Desktop/Studies/Sem5/DE/DE%20Project/payment-gateway/docs/specs/02_COMMON_SPEC.md#L127-L160)  
**Database:** `catalog_db` (Isolated schema and write credentials)

## Scope
Provides lexical, facet, and hybrid vector search over normalized Flipkart product listings. Holds authoritative price calculation, quote generation, and the local stock read model updated via Kafka inventory events.
