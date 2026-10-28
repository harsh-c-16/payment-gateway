"""Loopback-only P6 subprocess fixture. Explicit event double opt-in is mandatory."""

import argparse
import os

import uvicorn

from services.conversation.app import create_app
from services.conversation.database import Database
from services.conversation.state import ConversationState

from .doubles import EventCaptureDouble


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--test-double-events", action="store_true", required=True)
    parser.add_argument("--test-double-workflow", action="store_true")
    parser.add_argument("--lose-order-response", action="store_true")
    parser.add_argument("--catalog-unavailable", action="store_true")
    args = parser.parse_args()
    database = Database(os.environ["P6_TEST_DATABASE_URL"])
    state = ConversationState(database, events=EventCaptureDouble())
    workflow = None
    if args.test_double_workflow:
        from services.conversation.workflow import FixedWorkflow

        from .workflow_doubles import WorkflowProviderDouble

        provider = WorkflowProviderDouble()
        provider.lose_order_response = args.lose_order_response
        provider.catalog_unavailable = args.catalog_unavailable
        workflow = FixedWorkflow(state, provider.gateway())
    elif args.lose_order_response or args.catalog_unavailable:
        parser.error("provider faults require --test-double-workflow")
    app = create_app(state=state, mode="stub", purpose="contract_test", workflow=workflow)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="error", access_log=False)


if __name__ == "__main__":
    main()
