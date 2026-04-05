## Description

<!-- What does this PR do? Why is it needed? -->

## Change type

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to change)
- [ ] Refactor / code quality (no functional change)
- [ ] Documentation update
- [ ] Infrastructure / deployment change

## Related issues

<!-- Link to any issues this PR addresses. Use "Closes #123" to auto-close. -->

Closes #

## How was this tested?

<!-- Describe the tests you added or ran. Include commands if helpful. -->

```bash
pytest tests/unit/ -v
```

## Checklist

- [ ] My code follows the style guide (`ruff check .` and `mypy .` pass locally)
- [ ] I have added or updated tests for any changed functionality
- [ ] All existing tests pass (`pytest tests/unit/ -v`)
- [ ] TypeScript compiles without errors (`cd ui && npx tsc --noEmit`)
- [ ] I have updated documentation (README, docs/) where relevant
- [ ] I have checked for security implications (OWASP Top 10, secret handling)
- [ ] I have not introduced new `any` types without an explanatory comment

## Performance implications

<!-- Does this change affect query latency, ingestion throughput, or memory usage?
     If yes, include benchmark numbers or explain why the impact is acceptable. -->

N/A

## Screenshots / diagrams

<!-- For UI changes or architectural updates, include screenshots or updated diagrams. -->
