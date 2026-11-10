
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Activity, FileText, AlertCircle, CheckCircle } from "lucide-react"

export default function MedicalDashboard() {
  const data = props

  const metrics = [
    {
      title: "Total Tests",
      value: data.total_tests ?? 0,
      Icon: Activity,
    },
    {
      title: "Not Flagged",
      value: data.normal_tests ?? 0,
      Icon: CheckCircle,
    },
    {
      title: "Flagged Results",
      value: data.abnormal_tests ?? 0,
      Icon: AlertCircle,
    },
    {
      title: "Total Reports",
      value: data.total_reports ?? 0,
      Icon: FileText,
    },
  ]

  return (
    <div className="grid grid-cols-2 gap-3 p-2">
      {metrics.map(({ title, value, Icon }) => (
        <Card key={title}>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Icon size={16} />
              {title}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-semibold">{value}</div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
