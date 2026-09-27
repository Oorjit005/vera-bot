from app.validate import CASE_STUDY_BODIES, check_plagiarism


def test_exact_case_study_copy_flagged():
    for cs in CASE_STUDY_BODIES:
        assert check_plagiarism(cs) == ["PLAGIARISM"]


def test_near_copy_flagged():
    cs = CASE_STUDY_BODIES[0]
    near_copy = cs.replace("Meera", "Sameer")
    assert check_plagiarism(near_copy) == ["PLAGIARISM"]


def test_unrelated_message_not_flagged():
    body = "Suresh, DC vs MI at Arun Jaitley Stadium tonight, 7pm. Reply YES and I'll get the banner ready."
    assert check_plagiarism(body) == []


def test_thematically_similar_but_different_wording_not_flagged():
    body = (
        "Sushma, a quick check on The Beauty Bar: 22 calls in the last 30 days against a "
        "28-call average for metro salons, even though your profile CTR is healthy. People are "
        "finding you but not picking up the phone. Want me to list 'Haircut @ ₹99' on your "
        "profile as a call-driver? Reply YES and I'll get it ready."
    )
    assert check_plagiarism(body) == []
