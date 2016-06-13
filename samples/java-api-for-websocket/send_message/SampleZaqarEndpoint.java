/*
 * Licensed under the Apache License, Version 2.0 (the "License"); you may not
 * use this file except in compliance with the License.  You may obtain a copy
 * of the License at
 *
 *    http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
 * License for the specific language governing permissions and limitations under
 * the License.
 */
import java.io.IOException;

import javax.websocket.ClientEndpoint;
import javax.websocket.OnOpen;
import javax.websocket.RemoteEndpoint;
import javax.websocket.Session;

@ClientEndpoint
public final class SampleZaqarEndpoint {

    @OnOpen
    public void onOpen(final Session sess) throws IOException {
        final RemoteEndpoint.Basic remote = sess.getBasicRemote();

        final String authenticateMsg = "{\"action\":\"authenticate\","
                + "\"headers\":{\"X-Auth-Token\":"
                + "\"8444886dd9b04a1b87ddb502b508261c\",\"X-Project-ID\":"
                + "\"7530fad032ca431e9dc8ed4a5de5d99c\"}}"; // refer to bug
                                                            // #1553398

        remote.sendText(authenticateMsg);

        final String messagePostMsg = "{\"action\":\"message_post\",\"body\":"
                + "{\"messages\":[{\"body\":\"Zaqar Sample\"}],\"queue_name\":"
                + "\"SampleQueue\"},\"headers\":{\"Client-ID\":"
                + "\"355186cd-d1e8-4108-a3ac-a2183697232a\",\"X-Project-ID\":"
                + "\"7530fad032ca431e9dc8ed4a5de5d99c\"}}";

        remote.sendText(messagePostMsg);
    }

}
