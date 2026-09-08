"""Conservative text segmentation; retain original text separately for audit."""

import re


def routing_text(text: str) -> str:
    # Stop at recipients/signature; neither is evidence of the requested task.
    body = re.split(r"(?im)^\s*Nơi nhận\s*:", text)[0]
    # An explicitly numbered assignment to the department takes precedence.
    assignment = re.search(
        r"(?im)^\s*(?:\d+[.)]\s*)?Sở Nông nghiệp và Môi trường\s*:\s*", body
    )
    if assignment:
        body = body[assignment.end() :]
        body = re.split(
            r"(?im)^\s*\d+[.)]\s+(?:Sở|UBND|Ủy ban|Ban|Văn phòng|Các)\b", body
        )[0]
    else:
        lines = body.splitlines()
        start = next(
            (
                i
                for i, line in enumerate(lines)
                if re.match(
                    r"\s*(?:V/v|Về việc|Trích yếu|Kính gửi)\b", line, re.IGNORECASE
                )
            ),
            None,
        )
        if start is not None:
            lines = lines[start:]
        body = "\n".join(
            line
            for line in lines
            if not re.match(
                r"\s*(?:Căn cứ|Nơi nhận|Kính gửi|Số\s*:|CỘNG H[ÒO]A|Độc lập|"
                r"SỞ\s+|ỦY BAN NHÂN DÂN|UBND\s+|BỘ\s+)",
                line,
                re.IGNORECASE,
            )
        )
    return body.strip()
