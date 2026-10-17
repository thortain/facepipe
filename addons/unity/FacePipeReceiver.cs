// Add to a GameObject, assign an ARKit-compatible SkinnedMeshRenderer, then
// send FacePipe text v2 to this private UDP port.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using UnityEngine;

public sealed class FacePipeReceiver : MonoBehaviour
{
    public SkinnedMeshRenderer faceMesh;
    public Transform head;
    public Transform leftEye;
    public Transform rightEye;
    public string bindAddress = "127.0.0.1";
    public int port = 49985;

    private UdpClient client;
    private Thread receiveThread;
    private volatile bool running;
    private string latestFrame;
    private readonly Dictionary<string, int> shapeIndices =
        new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);

    private void OnEnable()
    {
        if (!IPAddress.TryParse(bindAddress, out IPAddress address) || !IsPrivate(address))
        {
            Debug.LogError("FacePipe requires a loopback or private IPv4 bind address.", this);
            enabled = false;
            return;
        }
        if (port < 1 || port > 65535)
        {
            Debug.LogError("FacePipe UDP port must be between 1 and 65535.", this);
            enabled = false;
            return;
        }
        shapeIndices.Clear();
        if (faceMesh != null && faceMesh.sharedMesh != null)
        {
            Mesh mesh = faceMesh.sharedMesh;
            for (int i = 0; i < mesh.blendShapeCount; i++)
                shapeIndices[mesh.GetBlendShapeName(i)] = i;
        }
        try
        {
            client = new UdpClient(new IPEndPoint(address, port));
            client.Client.ReceiveTimeout = 200;
            running = true;
            receiveThread = new Thread(ReceiveLoop) { IsBackground = true, Name = "FacePipe UDP" };
            receiveThread.Start();
        }
        catch (SocketException error)
        {
            Debug.LogError("FacePipe could not bind UDP: " + error.Message, this);
            enabled = false;
        }
    }

    private static bool IsPrivate(IPAddress address)
    {
        if (address.AddressFamily != AddressFamily.InterNetwork) return false;
        byte[] b = address.GetAddressBytes();
        return b[0] == 127 || b[0] == 10 ||
               (b[0] == 172 && b[1] >= 16 && b[1] <= 31) ||
               (b[0] == 192 && b[1] == 168) ||
               (b[0] == 100 && b[1] >= 64 && b[1] <= 127);
    }

    private void ReceiveLoop()
    {
        IPEndPoint peer = new IPEndPoint(IPAddress.Any, 0);
        while (running)
        {
            try
            {
                byte[] bytes = client.Receive(ref peer);
                Interlocked.Exchange(ref latestFrame, System.Text.Encoding.UTF8.GetString(bytes));
            }
            catch (SocketException error)
            {
                if (error.SocketErrorCode != SocketError.TimedOut) break;
            }
            catch (ObjectDisposedException) { break; }
        }
    }

    private void Update()
    {
        string frame = Interlocked.Exchange(ref latestFrame, null);
        if (frame != null) Apply(frame);
    }

    private void Apply(string frame)
    {
        foreach (string part in frame.Replace("___iFacialMocap", "").Split('|'))
        {
            if (part.Length == 0) continue;
            string token = part.TrimStart('=');
            int hash = token.IndexOf('#');
            if (hash >= 0)
            {
                ApplyPose(token.Substring(0, hash), token.Substring(hash + 1));
                continue;
            }
            int separator = token.IndexOf('&');
            if (separator < 0) separator = token.IndexOf('-');
            if (separator <= 0 || faceMesh == null) continue;
            string rawName = token.Substring(0, separator);
            string identifier = ToIdentifier(rawName);
            if (!shapeIndices.TryGetValue(identifier, out int index) &&
                !shapeIndices.TryGetValue(rawName, out index)) continue;
            if (float.TryParse(token.Substring(separator + 1), NumberStyles.Float,
                               CultureInfo.InvariantCulture, out float weight) &&
                !float.IsNaN(weight) && !float.IsInfinity(weight))
                faceMesh.SetBlendShapeWeight(index, weight);
        }
    }

    private static string ToIdentifier(string name)
    {
        if (name.EndsWith("_L", StringComparison.Ordinal))
            return name.Substring(0, name.Length - 2) + "Left";
        if (name.EndsWith("_R", StringComparison.Ordinal))
            return name.Substring(0, name.Length - 2) + "Right";
        return name;
    }

    private void ApplyPose(string name, string numbers)
    {
        Transform target = null;
        if (name.Equals("head", StringComparison.OrdinalIgnoreCase)) target = head;
        else if (name.Equals("leftEye", StringComparison.OrdinalIgnoreCase)) target = leftEye;
        else if (name.Equals("rightEye", StringComparison.OrdinalIgnoreCase)) target = rightEye;
        if (target == null) return;
        string[] parts = numbers.Split(',');
        if (parts.Length < 3) return;
        float[] pose = new float[Math.Min(parts.Length, 6)];
        for (int i = 0; i < pose.Length; i++)
            if (!float.TryParse(parts[i], NumberStyles.Float, CultureInfo.InvariantCulture,
                                out pose[i]) || float.IsNaN(pose[i]) || float.IsInfinity(pose[i]))
                return;
        target.localRotation = Quaternion.Euler(pose[0], pose[1], pose[2]);
        if (target == head && pose.Length >= 6)
            target.localPosition = new Vector3(pose[3], pose[4], pose[5]);
    }

    private void OnDisable()
    {
        running = false;
        client?.Close();
        client = null;
        if (receiveThread != null && receiveThread.IsAlive)
            receiveThread.Join(500);
        receiveThread = null;
    }
}
