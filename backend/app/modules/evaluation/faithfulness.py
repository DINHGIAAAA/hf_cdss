async def evaluate_faithfulness(
    question: str,
    answer: str,
    evidence_chunks: list[EvidenceChunk],
) -> float:
    """Score 0-1: câu trả lời có chỉ dùng thông tin từ evidence không."""
    prompt = f"""
    Evidence: {[c.text for c in evidence_chunks]}
    Answer: {answer}
    Rate 0.0-1.0: does every factual claim in the answer appear in the evidence?
    Respond with only a number.
    """
    score = await call_llm_float(prompt)
    return score