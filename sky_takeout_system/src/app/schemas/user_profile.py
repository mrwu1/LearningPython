from typing import List, Optional

from pydantic import Field, BaseModel


#Union[T, None]
class UserDietaryProfile(BaseModel):

    user_id: str = Field(..., description="Customer user identifier")
    allergies:List[str] = Field(default_factory=list, description="Strict medical allergens (e.g., peanut, shrimp)")
    disliked_ingredients: List[str] = Field(default_factory=list,description="Preferences to avoid (e.g., coriander,onion")
    diet_style:Optional[str] = Field(default="standard", description="Lifestyle (e.g., keto, vegan, low_carb,standard")
    target_calories_per_meal:Optional[int] = Field(default=None, description="Preferred calorie ceiling")

    # 2. 开放式长尾事实池 (Open-Ended Semantic Facts - 彻底解决所有冷门需求！)
    # -------------------------------------------------------------------------
    open_facts: List[str] = Field(
        default_factory=list,
        description="所有无法被固定字段归类的、冷门但重要的个性化事实与习惯"
    )

    def to_system_prompt_clause(self)->str:
        """Renders customer profile into an authoritative prompt constraint block."""
        clauses = []
        if self.allergies:
            clauses.append(f"- 🚨 STRICT MEDICAL ALLERGENS (NEVER RECOMMEND): {', '.join(self.allergies)}")
        if self.disliked_ingredients:
            clauses.append(f"- Disliked Ingredients (Avoid if possible): {', '.join(self.disliked_ingredients)}")
        if self.diet_style and self.diet_style != "standard":
            clauses.append(f"- Dietary Lifestyle Preference: {self.diet_style}")
        if self.target_calories_per_meal:
            clauses.append(f"- Preferred Calorie Limit: < {self.target_calories_per_meal} kcal")
        # 核心修复 3: 将冷门开放事实无死角渲染进 Prompt
        if self.open_facts:
            facts_lines = "\n  * ".join(self.open_facts)
            clauses.append(f"- 📌 PERSONALIZED HABITS & LONG-TAIL CONTEXT:\n  * {facts_lines}")
        if not clauses:
            return "No specific dietary restrictions recorded."
        return "\n".join(clauses)

    # to_system_prompt_clause()是企业级 Prompt Engineering
    # │ 的标准模式：将结构化数据库对象（DTO）一键转成大模型能无歧义理解的强约束指令块。