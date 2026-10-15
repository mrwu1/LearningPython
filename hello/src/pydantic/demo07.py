from datetime import date

from pydantic import BaseModel, model_validator


class Event(BaseModel):
    title: str
    start_date: date
    end_date: date

    # 跨字段校验器：对齐 java 类级别的校验逻辑
    @model_validator(mode="after")
    def verify_date_range(self) -> "Event":
        if self.end_date < self.start_date:
            raise ValueError("End date must be after start date")
        return self


# test
front_end = {
    "title": "Test Event",
    "start_date": "2023-01-04",
    "end_date": "2023-01-02",
}
r = Event.model_validate(front_end)
print(r)
