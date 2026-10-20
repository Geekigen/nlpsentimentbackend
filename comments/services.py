from django.conf import settings

from comments.models import Comment, Delivery
from comments.queries import score_to_stars
from comments.sentiment import analyze_driver_comment


def submit_comment(*, delivery: Delivery, body: str, customer_name: str = "") -> Comment:
    """Store the comment before the classifier runs."""
    return Comment.objects.create(
        driver=delivery.driver,
        delivery=delivery,
        body=body,
        customer_name=customer_name,
        analysis_status=Comment.AnalysisStatus.SUBMITTED,
    )


def analyze_saved_comment(comment: Comment) -> Comment:
    """Run the classifier and store the sentiment on a submitted comment."""
    comment.analysis_status = Comment.AnalysisStatus.ANALYZING
    comment.save(update_fields=["analysis_status"])
    try:
        analysis = analyze_driver_comment(comment.body)
    except Exception:
        comment.analysis_status = Comment.AnalysisStatus.SUBMITTED
        comment.save(update_fields=["analysis_status"])
        raise

    comment.sentiment = analysis.sentiment
    comment.score = analysis.score
    comment.stars = score_to_stars(analysis.score)
    comment.summary = analysis.summary
    comment.aspects = analysis.aspects.model_dump()
    comment.highlights = analysis.highlights
    comment.model_name = settings.OPENAI_MODEL
    comment.analysis_status = Comment.AnalysisStatus.ANALYZED
    comment.save()
    return comment


def record_comment(*, delivery: Delivery, body: str, customer_name: str = "") -> Comment:
    """Submit a comment and score it in one step. Used by the MCP tool."""
    return analyze_saved_comment(
        submit_comment(delivery=delivery, body=body, customer_name=customer_name)
    )
