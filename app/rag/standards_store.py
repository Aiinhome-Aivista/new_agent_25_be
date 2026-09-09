from typing import List, Dict, Any, Optional

DEFAULT_STANDARDS = [
    {
        "rule_code": "STD-SEC-01",
        "language": "java",
        "framework": "spring-boot",
        "category": "security",
        "title": "Strict Input Validation with @Valid and Bean Validation",
        "description": "All incoming HTTP request DTOs in Spring Boot controllers must be annotated with @Valid or @Validated and have constraint annotations like @NotNull, @NotBlank, @Size, @Email on fields.",
        "bad_example": "public ResponseEntity<User> createUser(@RequestBody UserDto dto) { ... }",
        "good_example": "public ResponseEntity<User> createUser(@Valid @RequestBody UserDto dto) { ... }",
        "severity": "WARNING",
        "is_blocking": False
    },
    {
        "rule_code": "STD-SEC-02",
        "language": "java",
        "framework": "spring-boot",
        "category": "security",
        "title": "Prevention of SQL Injection via JPA/Hibernate Parameterization",
        "description": "Always use named or positional parameters (:param, ?1) in JPA / JPQL queries. Never concatenate user input directly into SQL strings.",
        "bad_example": "entityManager.createQuery(\"SELECT u FROM User u WHERE u.email = '\" + email + \"'\");",
        "good_example": "entityManager.createQuery(\"SELECT u FROM User u WHERE u.email = :email\").setParameter(\"email\", email);",
        "severity": "CRITICAL",
        "is_blocking": True
    },
    {
        "rule_code": "STD-ARCH-01",
        "language": "java",
        "framework": "spring-boot",
        "category": "architecture",
        "title": "Separation of Concerns: Controller vs Service vs Repository",
        "description": "Controllers should only handle HTTP concerns, request routing, and basic response mapping. Business logic must reside in @Service beans.",
        "bad_example": "@PostMapping public User create(@RequestBody User u) { db.save(u); sendEmail(u); return u; }",
        "good_example": "@PostMapping public ResponseEntity<UserDto> create(@Valid @RequestBody CreateUserRequest req) { return ResponseEntity.ok(userService.create(req)); }",
        "severity": "WARNING",
        "is_blocking": False
    },
    {
        "rule_code": "STD-TEST-01",
        "language": "java",
        "framework": "spring-boot",
        "category": "testing",
        "title": "Unit and Integration Testing with JUnit 5 & Mockito",
        "description": "Every newly added public service method and controller endpoint must have corresponding JUnit 5 test methods covering happy path, negative path (invalid inputs), and exception branches.",
        "bad_example": "// No test class or only empty test contextLoads()",
        "good_example": "@Test void shouldThrowBadRequestWhenEmailIsInvalid() { ... }",
        "severity": "WARNING",
        "is_blocking": False
    },
    {
        "rule_code": "STD-ERR-01",
        "language": "java",
        "framework": "spring-boot",
        "category": "error-handling",
        "title": "Global Exception Handling with @ControllerAdvice",
        "description": "Use @RestControllerAdvice / @ExceptionHandler for uniform REST error responses (RFC 7807 Problem Details or standardized ErrorResponse DTO) instead of raw 500 stack traces.",
        "bad_example": "catch(Exception e) { e.printStackTrace(); return null; }",
        "good_example": "@RestControllerAdvice public class GlobalExceptionHandler { @ExceptionHandler(EntityNotFoundException.class) ... }",
        "severity": "WARNING",
        "is_blocking": False
    },
    {
        "rule_code": "STD-PY-SEC-01",
        "language": "python",
        "framework": "flask",
        "category": "security",
        "title": "SQLAlchemy / DB-API Query Parameterization",
        "description": "Never format raw SQL queries using f-strings or % formatting. Always use parameterized queries (bind parameters :param, %s) or ORM filter queries.",
        "bad_example": "db.session.execute(f'SELECT * FROM users WHERE email = \"{email}\"')",
        "good_example": "db.session.execute(text('SELECT * FROM users WHERE email = :email'), {'email': email})",
        "severity": "CRITICAL",
        "is_blocking": True
    },
    {
        "rule_code": "STD-PY-QUAL-01",
        "language": "python",
        "framework": "flask",
        "category": "quality",
        "title": "Type Hinting and Pydantic DTO Schema Validation",
        "description": "Use type annotations (PEP 484) and Pydantic v2 models / Marshmallow schemas to validate request payloads before processing.",
        "bad_example": "data = request.get_json(); user_id = data['id']",
        "good_example": "try:\n    payload = UserCreateSchema(**request.get_json())\nexcept ValidationError as e:\n    return jsonify(e.errors()), 400",
        "severity": "WARNING",
        "is_blocking": False
    },
    {
        "rule_code": "STD-PY-TEST-01",
        "language": "python",
        "framework": "flask",
        "category": "testing",
        "title": "Automated Unit and Fixture Testing with Pytest",
        "description": "Every endpoint and service module must have corresponding pytest test cases in tests/ covering success, validation rejection (400), and unauthorized access (401/403).",
        "bad_example": "# No test_*.py files provided in repository",
        "good_example": "def test_create_user_invalid_email(client):\n    res = client.post('/api/users', json={'email': 'bad'})\n    assert res.status_code == 400",
        "severity": "WARNING",
        "is_blocking": False
    },
    {
        "rule_code": "STD-TS-QUAL-01",
        "language": "typescript",
        "framework": "react",
        "category": "quality",
        "title": "Strict TypeScript Typing (No any / unknown leak)",
        "description": "Explicitly type React props, state hooks, and API responses. Avoid using `any` type in application boundaries.",
        "bad_example": "const handleData = (data: any) => { ... }",
        "good_example": "const handleData = (data: UserResponseDTO) => { ... }",
        "severity": "WARNING",
        "is_blocking": False
    }
]

class StandardsStore:
    """RAG repository for enterprise coding standards and best-practice rules."""

    def __init__(self):
        self.standards: List[Dict[str, Any]] = list(DEFAULT_STANDARDS)

    def search_relevant_standards(self, language: str = "java", framework: str = "spring-boot", query: str = "") -> List[Dict[str, Any]]:
        """Retrieves matching approved standards based on language, framework, and diff content."""
        results = []
        q_lower = query.lower() if query else ""

        for std in self.standards:
            lang_match = std["language"] in (language.lower(), "general", "all")
            fw_match = std["framework"] in (framework.lower(), "all", "general")

            if lang_match and fw_match:
                # Check keyword relevance if query provided
                if not q_lower:
                    results.append(std)
                else:
                    keywords = [std["title"].lower(), std["category"].lower(), std["rule_code"].lower()]
                    if any(k in q_lower for k in keywords) or "controller" in q_lower or "repository" in q_lower or "test" in q_lower:
                        results.append(std)
                    elif len(results) < 3:
                        results.append(std) # include high-priority general baseline

        return results if results else self.standards[:4]

    def add_standard(self, standard: Dict[str, Any]) -> None:
        self.standards.append(standard)

standards_store = StandardsStore()
