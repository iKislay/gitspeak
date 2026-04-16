import dynamic from "next/dynamic";

// Load the full call interface only on the client — it uses browser APIs
// (getUserMedia, WebRTC) through the Vapi SDK.
const CallInterface = dynamic(
  () => import("@/components/CallInterface"),
  { ssr: false }
);

export default function Home() {
  return <CallInterface />;
}
