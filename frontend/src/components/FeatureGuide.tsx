const guides = {
  ad: {
    title: "How Active Directory works in HIOP",
    body: (
      <>
        <p>
          Active Directory is your organisation’s address book for staff and
          computers. This HIOP integration reads computer records to help
          identify discovered devices; it does not automatically enable staff
          sign-in.
        </p>
        <ol>
          <li>
            Ask your IT administrator for the domain-controller address and a
            service account that can read computer records.
          </li>
          <li>
            Enter your domain, secure LDAP server and port. LDAPS commonly uses
            636; StartTLS commonly uses 389.
          </li>
          <li>
            Enter the Base DN: the starting folder to search, such as
            DC=example,DC=com. A computer search base can narrow this to a
            specific folder.
          </li>
          <li>
            Save the connection and use Test connection. The backend must reach
            the directory server and trust its certificate.
          </li>
          <li>
            Enable the connection, run Active Directory enrichment from
            Discover, and review the identity suggestions.
          </li>
        </ol>
        <p>
          HIOP does not modify directory objects. The current local agent has
          no Active Directory adapter, so hosted collection requires a private
          network route from the backend. A saved connection is not evidence
          of a successful test.
        </p>
      </>
    ),
  },
  agent: {
    title: "How to connect a local agent",
    body: (
      <>
        <p>
          The agent is a helper that stays inside your property’s network. You
          use HIOP in a browser; the helper checks local devices and reports
          back.
        </p>
        <ol>
          <li>
            Choose a Windows computer that stays on and can reach the devices
            you want to monitor.
          </li>
          <li>Extract the HIOP Windows agent package and run Install HIOP Agent.cmd as an administrator.</li>
          <li>Select the property and create a one-time connection code.</li>
          <li>
            Open the HIOP Agent tray icon, choose <strong>Connect or enroll...</strong>,
            and paste the one-time code in the native agent window.
          </li>
          <li>
            Wait for Online status, select the same property in Discover, and
            start a small scan.
          </li>
        </ol>
        <p>
          Scanning uses ping and a small set of connection checks. A device can
          be online but block those checks. “No response” is not the same as
          “powered off.”
        </p>
        <p>
          Request the agent to stop its scan process. HIOP shows Stopping until
          it receives acknowledgement. If the agent loses its connection,
          acknowledgement cannot be immediate.
        </p>
      </>
    ),
  },
};

export function FeatureGuide({ kind }: { kind: keyof typeof guides }) {
  const guide = guides[kind];
  return (
    <details className="feature-guide">
      <summary>{guide.title}</summary>
      <div>{guide.body}</div>
    </details>
  );
}
