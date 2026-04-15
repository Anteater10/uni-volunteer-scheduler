import {
  Clock,
  CheckCircle,
  MapPin,
  PartyPopper,
  AlertTriangle,
  XCircle,
  Pause,
} from "lucide-react";

const MAP = {
  pending: { Icon: Clock, label: "Pending" },
  confirmed: { Icon: CheckCircle, label: "Confirmed" },
  checked_in: { Icon: MapPin, label: "Checked in" },
  attended: { Icon: PartyPopper, label: "Attended" },
  no_show: { Icon: AlertTriangle, label: "No-show" },
  cancelled: { Icon: XCircle, label: "Cancelled" },
  waitlisted: { Icon: Pause, label: "Waitlisted" },
};

export default function StatusIcon({ status, className = "h-5 w-5" }) {
  const entry = MAP[status] ?? MAP.pending;
  const { Icon, label } = entry;
  return <Icon className={className} aria-label={label} role="img" />;
}
