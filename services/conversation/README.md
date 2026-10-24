# Conversation Service (M1)

**Owner:** Jaineel Vora (B24CM1080)  
**Specification Brief:** [04_JAINEEL_VORA.md](file:///c:/Users/voraj/OneDrive/Desktop/Studies/Sem5/DE/DE%20Project/payment-gateway/docs/specs/04_JAINEEL_VORA.md)  
**Contract Authority:** [contracts/http/conversation.yaml](file:///c:/Users/voraj/OneDrive/Desktop/Studies/Sem5/DE/DE%20Project/payment-gateway/contracts/http/conversation.yaml) & [02_COMMON_SPEC.md §4](file:///c:/Users/voraj/OneDrive/Desktop/Studies/Sem5/DE/DE%20Project/payment-gateway/docs/specs/02_COMMON_SPEC.md#L127-L160)  
**Database:** `conversation_db` (Isolated schema and write credentials)

## Scope
Maintains shopping sessions, shopping carts, idempotent cart operations, and the agentic shopping assistant workflow. Communicates via HTTP clients with Catalogue (M2) and Orders (M3) services. Emits session events via the shared outbox library.
