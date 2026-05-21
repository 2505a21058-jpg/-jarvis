from __future__ import annotations

from agent.hands import ActionRouter, AppClassifier, HandsController
from agent.hands.engines.base import ok
from rawvision.capture.process_monitor import ProcessInfo
from rawvision.output.schema import AppType, ElementRole, ElementSource, UIElement


def test_hands_public_api_routes_cdp_clicks():
    calls = []

    class FakeCDP:
        def click(self, element):
            calls.append(("click", element.cdp_node_id))
            return ok("cdp", "clicked")

    router = ActionRouter(engines={"cdp": FakeCDP(), "sendinput": FakeCDP()})
    controller = HandsController(router=router)
    element = UIElement(
        name="Link",
        role=ElementRole.LINK,
        source=ElementSource.CDP,
        cdp_node_id=7,
    )
    process = ProcessInfo(app_type=AppType.CHROME, cdp_available=True)

    result = controller.click(element, process_info=process)

    assert result.success is True
    assert calls == [("click", 7)]


def test_app_classifier_terminal_route():
    route = AppClassifier().route_for(
        "run_command",
        None,
        ProcessInfo(app_type=AppType.TERMINAL),
    )

    assert route == "terminal"
