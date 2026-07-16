import unittest

from app.main import app
from app.schemas.ticket import TicketCreate, TicketResponse, TicketUpdate


class TicketContractTests(unittest.TestCase):
    def test_ticket_detail_route_is_registered(self):
        self.assertIn("/api/v1/tickets/{ticket_id}", app.openapi()["paths"])

    def test_ticket_response_exposes_updated_at(self):
        self.assertIn("updated_at", TicketResponse.model_fields)

    def test_supported_create_and_reopen_fields(self):
        create = TicketCreate(title="Test", description="Test", priority="High")
        reopen = TicketUpdate(status="Open")
        self.assertEqual(create.priority, "High")
        self.assertEqual(reopen.status, "Open")


if __name__ == "__main__":
    unittest.main()
