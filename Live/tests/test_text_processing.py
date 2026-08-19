import pytest
from bot.utils.text_processing import (
    normalize_trivia_answer,
    extract_question_concepts,
    calculate_concept_similarity
)


def test_normalize_trivia_answer():
    # Test punctuation removal
    assert normalize_trivia_answer("Red Dead Redemption 2!") == "red dead redemption 2"
    assert normalize_trivia_answer("GTA: V") == "grand theft auto v"
    
    # Test abbreviation expansion
    assert normalize_trivia_answer("gta v") == "grand theft auto v"
    assert normalize_trivia_answer("rdr2") == "red dead redemption 2"
    assert normalize_trivia_answer("LoZ") == "legend zelda" # "of" is a filler word and will be removed
    
    # Test filler word removal
    assert normalize_trivia_answer("The Legend of Zelda") == "legend legend zelda"
    assert normalize_trivia_answer("A Game of Thrones") == "game thrones"
    assert normalize_trivia_answer("roughly 100") == "100"


def test_extract_question_concepts():
    # Test metric extraction
    concepts = extract_question_concepts("How many episodes does this have?")
    assert "metric:episodes" in concepts
    
    # Test completion concepts
    concepts = extract_question_concepts("When was the game completed?")
    assert "concept:completion" in concepts
    
    # Test comparison
    concepts = extract_question_concepts("Which is better: GTA V or RDR2?")
    assert "concept:comparison" in concepts
    
    # Test entity extraction (capitalized words)
    concepts = extract_question_concepts("How many times did Jonesy play Elden Ring?")
    assert "entity:elden ring" in concepts
    # 'jonesy' should be excluded based on the function rules
    assert "entity:jonesy" not in concepts


def test_calculate_concept_similarity():
    # Exact match
    c1 = {"metric:episodes", "entity:elden", "entity:ring"}
    c2 = {"metric:episodes", "entity:elden", "entity:ring"}
    assert calculate_concept_similarity(c1, c2) == 1.0
    
    # Partial match (2 out of 4 distinct concepts in union: 1 shared, 2 unique = 1/3)
    c3 = {"entity:elden"}
    c4 = {"entity:ring"}
    # intersection: 0, union: 2
    assert calculate_concept_similarity(c3, c4) == 0.0
    
    # Partial match 2
    c5 = {"metric:episodes", "entity:elden"}
    c6 = {"metric:episodes", "entity:ring"}
    # intersection: 1 (metric:episodes), union: 3
    assert calculate_concept_similarity(c5, c6) == 1.0 / 3.0
    
    # Empty sets
    assert calculate_concept_similarity(set(), set()) == 0.0
    assert calculate_concept_similarity(c1, set()) == 0.0
