"""Bounded analytics persistence helpers; business calculations live in services."""
from sqlalchemy import select

from app.models.analytics import AnalyticsAggregate


class AnalyticsRepository:
    def __init__(self, db, model):
        self.db, self.model = db, model

    def get(self, object_id):
        return self.db.get(self.model, object_id)

    def page(self, filters=(), page=1, page_size=50, order_by=None):
        query = self.db.query(self.model).filter(*filters)
        total = query.count()
        if order_by is not None:
            query = query.order_by(order_by)
        return query.offset((page - 1) * page_size).limit(page_size).all(), total

    def create(self, **values):
        row = self.model(**values)
        self.db.add(row)
        return row


class AnalyticsAggregateRepository(AnalyticsRepository):
    def __init__(self, db):
        super().__init__(db, AnalyticsAggregate)

    def upsert(self, values):
        identity = {key: values[key] for key in ("metric_definition_id", "entity_type", "entity_id", "bucket_start", "bucket_size")}
        row = self.db.scalar(select(AnalyticsAggregate).filter_by(**identity))
        if not row:
            row = AnalyticsAggregate(**values)
            self.db.add(row)
        else:
            for key, value in values.items():
                setattr(row, key, value)
        return row
